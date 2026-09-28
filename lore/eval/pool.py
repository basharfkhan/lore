"""Pool candidate documents for labelling each eval case.

For every case, the case query and each hindsight query are run through each retriever with the
case's cutoff, and the top documents from each are merged into a worksheet listing every
candidate once, with the retriever/query/rank that found it and enough text to judge it.

Pools only grow: re-running with a new retriever adds its candidates and keeps the old ones, so
no retriever is graded only on documents it found itself. Any new candidate shows up as
unjudged in tests/test_eval.py until it is labelled.

    python -m lore.eval.pool                          # bm25, dense and hybrid
    python -m lore.eval.pool --retrievers dense
"""

from __future__ import annotations

import argparse
import json

from lore.eval.cases import POOL_DIR, load_cases
from lore.retrieve.bm25 import unique_docs
from lore.retrieve.registry import build_retrievers

PER_QUERY = 15
SNIPPET_CHARS = 700


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retrievers", nargs="+", default=["bm25", "dense", "hybrid"])
    args = parser.parse_args()

    retrievers = build_retrievers(args.retrievers)
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    for case in load_cases():
        path = POOL_DIR / f"{case.id}.jsonl"
        found: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                # Tags written before retrievers were named came from BM25.
                entry["found_by"] = [t if ":" in t else f"bm25:{t}" for t in entry["found_by"]]
                found[entry["doc_id"]] = entry
        before = len(found)

        queries = [("case", case.query)] + [
            (f"h{i}", q) for i, q in enumerate(case.hindsight_queries, 1)
        ]
        for retriever in retrievers:
            short = retriever.name.split("-")[0]
            for tag, query in queries:
                hits = unique_docs(retriever.search(query, 400, case.cutoff_iso), PER_QUERY)
                for rank, hit in enumerate(hits, 1):
                    entry = found.setdefault(
                        hit.doc_id,
                        {
                            "doc_id": hit.doc_id,
                            "title": hit.chunk["doc_title"],
                            "available_from": hit.chunk["available_from"],
                            "url": hit.chunk["url"],
                            "snippet": hit.chunk["text"][:SNIPPET_CHARS],
                            "found_by": [],
                        },
                    )
                    label = f"{short}:{tag}@{rank}"
                    if label not in entry["found_by"]:
                        entry["found_by"].append(label)

        with path.open("w", encoding="utf-8", newline="\n") as f:
            for entry in sorted(found.values(), key=lambda e: e["doc_id"]):
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  {case.id:14s} {len(found)} candidates ({len(found) - before} new)")


if __name__ == "__main__":
    main()
