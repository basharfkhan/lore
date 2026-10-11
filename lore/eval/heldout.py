"""Evaluate retrievers on the held-out cases: pool, judge, score.

The held-out cases (evals/heldout/cases.yaml) are obscure incidents the model does not
recognise, and no design choice was tuned on them. For each case:

1. the hidden failure mechanism is split into two parts, the same shape as the hand-written
   dev criteria, so the judge asks the same kind of question it was validated on;
2. every retriever's top documents are pooled, together with hybrid results for the hindsight
   queries, so the pool also holds precursors no retriever found from the description;
3. the checklist judge grades the pool;
4. each retriever is scored against those grades.

Cases whose pool holds no direct precursor are reported but left out of hit rates: nothing in
the archive could have warned about them.

    python -m lore.eval.heldout
"""

from __future__ import annotations

import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import yaml

from lore.eval.cases import EVAL_DIR, Case
from lore.eval.judge import judge_case, load_criteria
from lore.eval.metrics import first_rank, hit_at_k, ndcg_at_k, recall_at_k
from lore.llm import json_call
from lore.retrieve.bm25 import unique_docs
from lore.retrieve.registry import build_retrievers

HELDOUT_DIR = EVAL_DIR / "heldout"
RETRIEVERS = ["bm25", "dense", "hybrid", "hypotheses-bm25", "hypotheses"]
DEPTH = 30  # documents per retriever that are pooled and scored
HINDSIGHT_DEPTH = 10

CRITERIA_SYSTEM = """\
You prepare grading criteria for a pre-mortem evaluation. Given what actually went wrong in an \
incident, split the cause into two distinct parts, A and B, such that a lessons-learned \
document about both parts would be describing the same failure mechanism, and a document about \
only one would be describing a contributing factor.

Write each part as a short description of a kind of thing a document could be about, in \
generic engineering terms with no mission, program or hardware names. The parts must not \
overlap, and neither may be so broad that most engineering lessons would match it."""

CRITERIA_SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
    "required": ["a", "b"],
    "additionalProperties": False,
}


def load_heldout() -> list[Case]:
    data = yaml.safe_load((HELDOUT_DIR / "cases.yaml").read_text(encoding="utf-8"))
    cases = []
    for entry in data["cases"]:
        case = Case(
            id=entry["id"],
            mishap=entry["source_title"],
            report="",
            cutoff=date.fromisoformat(str(entry["cutoff"])),
            query=entry["query"],
            hindsight_queries=entry["hindsight_queries"],
            failure_mechanism=entry["failure_mechanism"],
        )
        case.difficulty = entry["difficulty"]
        cases.append(case)
    return cases


def make_criteria(case: Case, examples: dict[str, dict[str, str]]) -> dict[str, str]:
    shots = "\n\n".join(f"A: {c['a']}\nB: {c['b']}" for c in examples.values())
    user = (
        f"Examples of well-formed parts from other incidents:\n\n{shots}\n\n"
        f"What actually went wrong in this incident:\n{case.failure_mechanism}"
    )
    return json_call(CRITERIA_SYSTEM, user, CRITERIA_SCHEMA, max_tokens=4000)


def rankings(case: Case, retrievers: list) -> dict[str, list[str]]:
    return {
        r.name: [h.doc_id for h in unique_docs(r.search(case.query, 2000, case.cutoff_iso), DEPTH)]
        for r in retrievers
    }


def score(ranked: list[str], grades: dict[str, int]) -> dict:
    return {
        "hit@10": hit_at_k(ranked, grades, 10),
        "hit@30": hit_at_k(ranked, grades, 30),
        "recall@30": recall_at_k(ranked, grades, 30),
        "ndcg@10": ndcg_at_k(ranked, grades, 10),
        "first_direct_rank": first_rank(ranked, grades),
    }


def mean(values: list[float]) -> float:
    values = [v for v in values if not math.isnan(v)]
    return statistics.mean(values) if values else float("nan")


def main() -> None:
    cases = load_heldout()
    retrievers = build_retrievers(RETRIEVERS)
    hybrid = next(r for r in retrievers if r.name.startswith("hybrid"))
    examples = load_criteria()

    def prepare(case: Case) -> dict:
        ranked = rankings(case, retrievers)
        pool = {d for docs in ranked.values() for d in docs}
        for q in case.hindsight_queries:
            hits = unique_docs(hybrid.search(q, 400, case.cutoff_iso), HINDSIGHT_DEPTH)
            pool |= {h.doc_id for h in hits}
        criteria = make_criteria(case, examples)
        judged = judge_case(case, criteria, sorted(pool))
        return {"ranked": ranked, "criteria": criteria, "judged": judged}

    # Cases run a few at a time; each one's judge batches are already parallel.
    with ThreadPoolExecutor(max_workers=2) as pool:
        prepared = list(pool.map(prepare, cases))

    results = []
    for case, prep in zip(cases, prepared, strict=True):
        grades = {d: j["grade"] for d, j in prep["judged"].items()}
        relevant = {d: g for d, g in grades.items() if g > 0}
        results.append(
            {
                "case": case.id,
                "title": case.mishap,
                "difficulty": case.difficulty,
                "cutoff": case.cutoff_iso,
                "criteria": prep["criteria"],
                "pool_size": len(grades),
                "n_direct": sum(g == 2 for g in grades.values()),
                "n_related": sum(g == 1 for g in grades.values()),
                "direct": sorted(d for d, g in grades.items() if g == 2),
                "scores": {name: score(r, relevant) for name, r in prep["ranked"].items()},
                "judgments": prep["judged"],
            }
        )

    with_precursor = [r for r in results if r["n_direct"]]
    print(
        f"{len(results)} held-out cases; {len(with_precursor)} have a direct precursor in the "
        f"archive ({sum(r['difficulty'] == 'hard' for r in with_precursor)} hard)"
    )
    for r in results:
        print(
            f"  {r['case']:9s} {r['difficulty']:4s} pool {r['pool_size']:3d}  "
            f"direct {r['n_direct']}  related {r['n_related']:2d}  {r['title'][:55]}"
        )

    summary = {}
    for subset, rows in [
        ("all with a precursor", with_precursor),
        ("hard only", [r for r in with_precursor if r["difficulty"] == "hard"]),
    ]:
        print(f"\n{subset} ({len(rows)} cases)")
        print(f"  {'retriever':34s} hit@10 hit@30  R@30  nDCG@10")
        summary[subset] = {}
        for name in results[0]["scores"]:
            row = {
                m: mean([r["scores"][name][m] for r in rows])
                for m in ("hit@10", "hit@30", "recall@30", "ndcg@10")
            }
            summary[subset][name] = row
            print(
                f"  {name:34s} {row['hit@10']:6.2f} {row['hit@30']:6.2f} "
                f"{row['recall@30']:5.2f} {row['ndcg@10']:8.3f}"
            )

    path = EVAL_DIR / "results" / "heldout.json"
    path.write_text(
        json.dumps({"summary": summary, "cases": results}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n-> {path}")


if __name__ == "__main__":
    main()
