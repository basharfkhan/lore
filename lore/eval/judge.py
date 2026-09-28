"""LLM relevance judge, and its calibration against the human-reviewed dev labels.

Hand-labelling ~100 pooled candidates for each of 30 cases is not practical, so candidates for
the held-out cases are graded by Claude with the same rubric the dev labels use. The judge is
only trusted as far as it agrees with those labels, so calibration reports that agreement
(exact, weighted kappa, and precision/recall on "relevant" and "direct precursor").

The judge is told the real failure mechanism: it grades the way a human who knows the answer
does. The system under test never sees the mechanism.

    python -m lore.eval.judge calibrate
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from lore.data.llis import OUT_PATH as LLIS_PATH
from lore.eval.cases import EVAL_DIR, POOL_DIR, load_cases
from lore.llm import MODEL, json_call

BATCH = 15
DOC_CHARS = 1800
WORKERS = 8

SYSTEM = """\
You grade documents from NASA's lessons-learned archive for a pre-mortem evaluation. You are \
given a system as it stood before a real failure, the actual failure mechanism, and candidate \
documents that were all written before the failure. For each document decide whether an \
engineer reading it beforehand would have been warned about what went wrong.

Grades:
2 - direct precursor: the document describes the same failure mechanism or root cause, even \
if it happened to different hardware or a different program.
1 - related: a contributing factor to this failure, or a practice that would clearly have \
helped prevent it, but not the mechanism itself.
0 - not relevant: shares only topic, vocabulary or hardware type, or is generic advice that \
applies to any project.

Be strict. Most candidates are 0. A document that is about the same kind of spacecraft but a \
different failure is 0. Give each grade a one-sentence reason."""

SCHEMA = {
    "type": "object",
    "properties": {
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "grade": {"type": "integer", "enum": [0, 1, 2]},
                    "reason": {"type": "string"},
                },
                "required": ["doc_id", "grade", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["judgments"],
    "additionalProperties": False,
}


def document_texts(doc_ids: list[str], snippets: dict[str, str]) -> dict[str, str]:
    """Full lesson text for LLIS documents; for reports, the pooled chunk that matched."""
    lessons = {}
    with LLIS_PATH.open(encoding="utf-8") as f:
        for line in f:
            lesson = json.loads(line)
            lessons[lesson["id"]] = lesson
    texts = {}
    for doc_id in doc_ids:
        if doc_id in lessons:
            x = lessons[doc_id]
            body = "\n\n".join(
                p for p in [x["driving_event"], x["lesson"], x["recommendation"]] if p
            )
            texts[doc_id] = f"{x['title']}\n\n{body}"[:DOC_CHARS]
        else:
            texts[doc_id] = snippets.get(doc_id, doc_id)[:DOC_CHARS]
    return texts


def judge(description: str, mechanism: str, texts: dict[str, str]) -> dict[str, dict]:
    ids = sorted(texts)
    batches = [ids[start : start + BATCH] for start in range(0, len(ids), BATCH)]

    def ask(batch: list[str]) -> dict[str, dict]:
        docs = "\n\n".join(f'<document id="{d}">\n{texts[d]}\n</document>' for d in batch)
        user = (
            f"System before the failure:\n{description}\n\n"
            f"Actual failure mechanism:\n{mechanism}\n\nCandidates:\n\n{docs}"
        )
        result = json_call(SYSTEM, user, SCHEMA, max_tokens=8000)
        return {
            j["doc_id"]: {"grade": j["grade"], "reason": j["reason"]}
            for j in result["judgments"]
            if j["doc_id"] in batch
        }

    def run(batch: list[str]) -> dict[str, dict]:
        graded = ask(batch)
        # The model occasionally drops a document from a long batch; ask again for just those.
        for _ in range(2):
            missing = sorted(set(batch) - set(graded))
            if not missing:
                break
            graded |= ask(missing)
        missing = sorted(set(batch) - set(graded))
        if missing:
            raise RuntimeError(f"judge skipped {missing}")
        return graded

    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for graded in pool.map(run, batches):
            out.update(graded)
    return out


def weighted_kappa(pairs: list[tuple[int, int]], n: int = 3) -> float:
    """Quadratic-weighted Cohen's kappa for ordinal grades 0..n-1."""
    observed = Counter(pairs)
    total = len(pairs)
    rows = Counter(a for a, _ in pairs)
    cols = Counter(b for _, b in pairs)

    def w(i: int, j: int) -> float:
        return (i - j) ** 2 / (n - 1) ** 2

    obs = sum(w(i, j) * observed[(i, j)] for i in range(n) for j in range(n)) / total
    exp = sum(w(i, j) * rows[i] * cols[j] for i in range(n) for j in range(n)) / total**2
    return 1 - obs / exp if exp else float("nan")


def precision_recall(pairs: list[tuple[int, int]], threshold: int) -> tuple[float, float]:
    tp = sum(h >= threshold and j >= threshold for h, j in pairs)
    judged = sum(j >= threshold for _, j in pairs)
    human = sum(h >= threshold for h, _ in pairs)
    return (tp / judged if judged else float("nan"), tp / human if human else float("nan"))


def calibrate() -> None:
    per_case, all_pairs, disagreements = [], [], []
    for case in load_cases():
        pool = {
            json.loads(line)["doc_id"]: json.loads(line)["snippet"]
            for line in (POOL_DIR / f"{case.id}.jsonl").read_text(encoding="utf-8").splitlines()
        }
        texts = document_texts(sorted(case.labels), pool)
        judged = judge(case.query, case.failure_mechanism, texts)
        pairs = [(case.labels[d], judged[d]["grade"]) for d in sorted(case.labels)]
        all_pairs += pairs
        per_case.append((case.id, weighted_kappa(pairs), len(pairs)))
        disagreements += [
            {
                "case": case.id,
                "doc_id": d,
                "human": case.labels[d],
                "judge": judged[d]["grade"],
                "reason": judged[d]["reason"],
            }
            for d in sorted(case.labels)
            if abs(case.labels[d] - judged[d]["grade"]) >= 1
            and max(case.labels[d], judged[d]["grade"]) >= 1
        ]

    exact = statistics.mean(h == j for h, j in all_pairs)
    p1, r1 = precision_recall(all_pairs, 1)
    p2, r2 = precision_recall(all_pairs, 2)
    kappa = weighted_kappa(all_pairs)
    reviewed = all(c.reviewed for c in load_cases())
    print(f"{len(all_pairs)} judged pairs, reference labels human-reviewed: {reviewed}")
    print(f"exact agreement {exact:.2f}   weighted kappa {kappa:.2f}")
    print(f"relevant (>=1): judge precision {p1:.2f} recall {r1:.2f}")
    print(f"direct   (=2):  judge precision {p2:.2f} recall {r2:.2f}")
    for cid, k, n in per_case:
        print(f"  {cid:13s} kappa {k:.2f}  ({n} pairs)")
    matrix = Counter(all_pairs)
    print("confusion (rows human 0/1/2, cols judge 0/1/2):")
    for h in range(3):
        print("  ", [matrix[(h, j)] for j in range(3)])

    path = EVAL_DIR / "results" / "judge_calibration.json"
    report = {
        "model": MODEL,
        "pairs": len(all_pairs),
        "exact_agreement": exact,
        "weighted_kappa": kappa,
        "relevant_precision": p1,
        "relevant_recall": r1,
        "direct_precision": p2,
        "direct_recall": r2,
        "per_case_kappa": {cid: k for cid, k, _ in per_case},
        "disagreements": disagreements,
    }
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{len(disagreements)} disagreements -> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["calibrate"])
    parser.parse_args()
    calibrate()


if __name__ == "__main__":
    main()
