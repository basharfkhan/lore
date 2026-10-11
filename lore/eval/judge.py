"""LLM relevance judge that answers the same two questions as the human adjudicator.

Free-form 0/1/2 grading did not survive contact with three readers: the draft labels, the
first version of this judge and the human reviewer gave three different grades to the same
lessons. Each mishap's cause is therefore split into two parts (evals/criteria.yaml) and a
document is graded by whether it is about each one: both is a 2 (direct precursor), one is a 1
(related), neither is a 0.

The judge is checked against the human answers in evals/review/adjudication_checklist.md.
Those rows are the ones the earlier judge and the draft labels disagreed on, so they are the
hard cases, not a random sample; agreement on them is a lower bound.

The judge is told the real failure mechanism. The system under test never sees it.

    python -m lore.eval.judge calibrate    # agreement with the human answers
    python -m lore.eval.judge regrade      # write judge grades for every dev label
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import yaml
from rank_bm25 import BM25Okapi

from lore.data.llis import OUT_PATH as LLIS_PATH
from lore.eval.adjudicate import SHEET, read_sheet
from lore.eval.cases import EVAL_DIR, load_cases
from lore.llm import MODEL, json_call
from lore.retrieve.bm25 import CHUNKS_PATH, tokenize

CRITERIA_PATH = EVAL_DIR / "criteria.yaml"
RESULTS_DIR = EVAL_DIR / "results"
BATCH = 12
DOC_CHARS = 1800
REPORT_PASSAGES = 3
WORKERS = 4

SYSTEM = """\
You grade documents from NASA's lessons-learned archive for a pre-mortem evaluation. You are \
given what actually went wrong in a real failure, split into two parts, A and B, and candidate \
documents written before that failure. For each document answer two yes/no questions: is the \
document about part A, and is it about part B?

Answer yes only when the document is really about that thing: it describes an event where it \
happened, or gives a lesson or recommendation specifically about it. Answer no when the \
document merely mentions it in passing, shares the topic or hardware type, or gives generic \
advice (test thoroughly, review designs, follow procedures) that would apply to any project. \
The two answers are independent. Most documents are no on both.

Give one sentence of reasoning per document."""

SCHEMA = {
    "type": "object",
    "properties": {
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "about_a": {"type": "boolean"},
                    "about_b": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["doc_id", "about_a", "about_b", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["judgments"],
    "additionalProperties": False,
}


def load_criteria() -> dict[str, dict[str, str]]:
    return yaml.safe_load(CRITERIA_PATH.read_text(encoding="utf-8"))


def document_texts(doc_ids: list[str], focus: str) -> dict[str, str]:
    """Text shown to the judge: the whole lesson, or a report's passages closest to ``focus``.

    A report is hundreds of pages, so the judge reads its few passages that best match the
    failure being graded. Showing one arbitrary pooled excerpt had the judge grading the
    Challenger report on a paragraph about heat-shield temperatures.
    """
    lessons = {}
    with LLIS_PATH.open(encoding="utf-8") as f:
        for line in f:
            lesson = json.loads(line)
            lessons[lesson["id"]] = lesson
    report_ids = {d for d in doc_ids if d not in lessons}
    report_chunks: dict[str, list[dict]] = {d: [] for d in report_ids}
    if report_ids:
        with CHUNKS_PATH.open(encoding="utf-8") as f:
            for line in f:
                chunk = json.loads(line)
                if chunk["doc_id"] in report_ids:
                    report_chunks[chunk["doc_id"]].append(chunk)

    texts = {}
    for doc_id in doc_ids:
        if doc_id in lessons:
            x = lessons[doc_id]
            body = "\n\n".join(
                p for p in [x["driving_event"], x["lesson"], x["recommendation"]] if p
            )
            texts[doc_id] = f"{x['title']}\n\n{body}"[:DOC_CHARS]
            continue
        chunks = report_chunks[doc_id]
        scores = BM25Okapi([tokenize(c["text"]) for c in chunks]).get_scores(tokenize(focus))
        best = sorted(range(len(chunks)), key=scores.__getitem__, reverse=True)[:REPORT_PASSAGES]
        passages = "\n\n[...]\n\n".join(chunks[i]["text"][: DOC_CHARS // 2] for i in sorted(best))
        texts[doc_id] = f"{chunks[0]['doc_title']} (excerpts)\n\n{passages}"
    return texts


def judge(mechanism: str, criteria: dict[str, str], texts: dict[str, str]) -> dict[str, dict]:
    """Return {doc_id: {"a": bool, "b": bool, "grade": int, "reason": str}}."""
    ids = sorted(texts)
    batches = [ids[start : start + BATCH] for start in range(0, len(ids), BATCH)]
    header = (
        f"What actually went wrong:\n{mechanism}\n\n"
        f"Part A: {criteria['a']}\nPart B: {criteria['b']}\n\nCandidates:\n\n"
    )

    def ask(batch: list[str]) -> dict[str, dict]:
        docs = "\n\n".join(f'<document id="{d}">\n{texts[d]}\n</document>' for d in batch)
        result = json_call(SYSTEM, header + docs, SCHEMA, max_tokens=8000)
        return {
            j["doc_id"]: {
                "a": j["about_a"],
                "b": j["about_b"],
                "grade": int(j["about_a"]) + int(j["about_b"]),
                "reason": j["reason"],
            }
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


def judge_case(case, criteria: dict[str, str], doc_ids: list[str]) -> dict[str, dict]:
    focus = f"{case.failure_mechanism} {criteria['a']} {criteria['b']}"
    return judge(case.failure_mechanism, criteria, document_texts(doc_ids, focus))


def calibrate() -> None:
    cases = {c.id: c for c in load_cases()}
    criteria = load_criteria()
    human, _ = read_sheet(
        SHEET.read_text(encoding="utf-8"), {c.mishap: c.id for c in cases.values()}
    )
    by_case: dict[str, list[str]] = {}
    for case_id, doc_id in human:
        by_case.setdefault(case_id, []).append(doc_id)

    rows, pairs = [], []
    for case_id, doc_ids in by_case.items():
        judged = judge_case(cases[case_id], criteria[case_id], sorted(doc_ids))
        for doc_id in sorted(doc_ids):
            h, j = human[(case_id, doc_id)], judged[doc_id]
            pairs.append((h, j["grade"]))
            rows.append({"case": case_id, "doc_id": doc_id, "human": h, **j})

    exact = statistics.mean(h == j for h, j in pairs)
    within_one = statistics.mean(abs(h - j) <= 1 for h, j in pairs)
    kappa = weighted_kappa(pairs)
    p2, r2 = precision_recall(pairs, 2)
    print(f"{len(pairs)} human-adjudicated rows (the hard cases)")
    print(f"exact agreement {exact:.2f}   within one grade {within_one:.2f}   kappa {kappa:.2f}")
    print(f"direct precursor (=2): judge precision {p2:.2f} recall {r2:.2f}")
    matrix = Counter(pairs)
    print("confusion (rows human 0/1/2, cols judge 0/1/2):")
    for h in range(3):
        print("  ", [matrix[(h, j)] for j in range(3)])
    for r in rows:
        if r["human"] != r["grade"]:
            print(
                f"  {r['case']:13s} {r['doc_id']:10s} you {r['human']} judge {r['grade']} "
                f"(A={'y' if r['a'] else 'n'} B={'y' if r['b'] else 'n'}) {r['reason'][:110]}"
            )

    report = {
        "model": MODEL,
        "rows": len(pairs),
        "exact_agreement": exact,
        "within_one": within_one,
        "weighted_kappa": kappa,
        "direct_precision": p2,
        "direct_recall": r2,
        "judgments": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "judge_calibration.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def regrade() -> None:
    """Judge every labelled dev document with the checklist; humans win where they answered."""
    cases = load_cases()
    criteria = load_criteria()
    human, _ = read_sheet(SHEET.read_text(encoding="utf-8"), {c.mishap: c.id for c in cases})
    out = {}
    for case in cases:
        judged = judge_case(case, criteria[case.id], sorted(case.labels))
        changed = Counter()
        for doc_id, j in judged.items():
            if (case.id, doc_id) in human:
                j["grade"] = human[(case.id, doc_id)]
                j["source"] = "human"
            else:
                j["source"] = "judge"
            changed[(case.labels[doc_id], j["grade"])] += 1
        out[case.id] = judged
        moved = sum(n for (old, new), n in changed.items() if old != new)
        direct = sorted(d for d, j in judged.items() if j["grade"] == 2)
        print(f"{case.id:13s} {len(judged)} docs, {moved} grades changed, direct: {direct}")
    path = RESULTS_DIR / "judge_regrade.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"-> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["calibrate", "regrade"])
    args = parser.parse_args()
    {"calibrate": calibrate, "regrade": regrade}[args.command]()


if __name__ == "__main__":
    main()
