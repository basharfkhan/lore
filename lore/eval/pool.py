"""Pool candidate documents for labelling each eval case.

For every case, the case query and each hindsight query are run through BM25 with the case's
cutoff, and the top documents from each are merged. The result is a worksheet listing each
candidate once, with the queries that found it and enough text to judge it.

BM25 is the only pooling source for now, which biases labels towards documents that share
vocabulary with the queries. Once the embedding retriever exists it is added to the pool and
any new candidates are judged, so neither retriever is graded only on what it found itself.

    python -m lore.eval.pool
"""

from __future__ import annotations

import json

from lore.eval.cases import POOL_DIR, load_cases
from lore.retrieve.bm25 import BM25Retriever, unique_docs

PER_QUERY = 15
SNIPPET_CHARS = 700


def main() -> None:
    retriever = BM25Retriever.from_file()
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    for case in load_cases():
        found: dict[str, dict] = {}
        queries = [("case", case.query)] + [
            (f"h{i}", q) for i, q in enumerate(case.hindsight_queries, 1)
        ]
        for tag, query in queries:
            for rank, hit in enumerate(
                unique_docs(retriever.search(query, 300, case.cutoff_iso), PER_QUERY), 1
            ):
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
                entry["found_by"].append(f"{tag}@{rank}")
        path = POOL_DIR / f"{case.id}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for entry in sorted(found.values(), key=lambda e: e["doc_id"]):
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  {case.id:14s} {len(found)} candidates -> {path.name}")


if __name__ == "__main__":
    main()
