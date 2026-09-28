"""Score a retriever on the historical pre-mortem cases.

Only the case description goes to the retriever, restricted to material available before the
mishap. Ranking is scored at document level (the first chunk of each document counts).

    python -m lore.eval.run                       # bm25, dense and hybrid
    python -m lore.eval.run --retrievers bm25
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import UTC, datetime

from lore.eval.cases import EVAL_DIR, load_cases
from lore.eval.metrics import first_rank, hit_at_k, ndcg_at_k, recall_at_k
from lore.retrieve.bm25 import unique_docs
from lore.retrieve.registry import build_retrievers

RESULTS_DIR = EVAL_DIR / "results"
DEPTH = 100  # documents ranked per case; first_rank beyond this is reported as a miss


def evaluate(retriever, cases) -> dict:
    rows = []
    for case in cases:
        hits = unique_docs(retriever.search(case.query, 2000, case.cutoff_iso), DEPTH)
        ranked = [h.doc_id for h in hits]
        rel = case.relevant
        rows.append(
            {
                "case": case.id,
                "reviewed": case.reviewed,
                "n_relevant": len(rel),
                "n_direct": sum(g == 2 for g in rel.values()),
                "hit@10": hit_at_k(ranked, rel, 10),
                "recall@10": recall_at_k(ranked, rel, 10),
                "recall@20": recall_at_k(ranked, rel, 20),
                "ndcg@10": ndcg_at_k(ranked, rel, 10),
                "first_direct_rank": first_rank(ranked, rel),
                "unjudged@10": sum(d not in case.labels for d in ranked[:10]),
                "top10": ranked[:10],
            }
        )
        if hypotheses := getattr(retriever, "last_hypotheses", None):
            rows[-1]["hypotheses"] = [vars(h) for h in hypotheses]
    metrics = ["hit@10", "recall@10", "recall@20", "ndcg@10"]
    mean = {m: statistics.mean(r[m] for r in rows if not math.isnan(r[m])) for m in metrics}
    return {"retriever": retriever.name, "cases": rows, "mean": mean}


def report(result: dict) -> None:
    columns = ["hit@10", "R@10", "R@20", "nDCG@10", "1st direct", "unjudged@10"]
    widths = [6, 6, 6, 8, 10, 11]
    header = f"{'case':14s} " + " ".join(f"{c:>{w}s}" for c, w in zip(columns, widths, strict=True))
    print(f"\nretriever: {result['retriever']}\n{header}")
    for r in result["cases"]:
        rank = r["first_direct_rank"] or f">{DEPTH}"
        print(
            f"{r['case']:14s} {r['hit@10']:6.0f} {r['recall@10']:6.2f} {r['recall@20']:6.2f} "
            f"{r['ndcg@10']:8.3f} {rank!s:>10s} {r['unjudged@10']:11d}"
        )
    m = result["mean"]
    print(
        f"{'mean':14s} {m['hit@10']:6.2f} {m['recall@10']:6.2f} "
        f"{m['recall@20']:6.2f} {m['ndcg@10']:8.3f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retrievers", nargs="+", default=["bm25", "dense", "hybrid"])
    args = parser.parse_args()

    cases = [c for c in load_cases() if c.labels]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for retriever in build_retrievers(args.retrievers):
        result = evaluate(retriever, cases)
        result["run_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        report(result)
        path = RESULTS_DIR / f"{result['retriever']}.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    unreviewed = [c.id for c in cases if not c.reviewed]
    if unreviewed:
        print(f"\nlabels not yet human-reviewed: {', '.join(unreviewed)}")


if __name__ == "__main__":
    main()
