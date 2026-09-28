"""Hybrid retrieval: reciprocal rank fusion of keyword and dense rankings.

RRF uses only ranks, so it needs no score calibration between BM25's unbounded scores and cosine
similarity. A chunk ranked well by either retriever rises; one ranked well by both rises most.
"""

from __future__ import annotations

from lore.retrieve.bm25 import Hit

RRF_K = 60  # the constant from Cormack et al. (2009); dampens the weight of the very top ranks
CANDIDATES = 200  # per retriever, before fusion


class HybridRetriever:
    def __init__(self, *retrievers, k: int = RRF_K):
        self.retrievers = retrievers
        self.k = k
        self.name = "hybrid-" + "+".join(r.name for r in retrievers)

    def search(self, query: str, k: int = 20, before: str | None = None) -> list[Hit]:
        fused: dict[str, float] = {}
        chunks: dict[str, Hit] = {}
        for retriever in self.retrievers:
            for rank, hit in enumerate(retriever.search(query, max(k, CANDIDATES), before), 1):
                fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (self.k + rank)
                chunks.setdefault(hit.chunk_id, hit)
        order = sorted(fused, key=fused.__getitem__, reverse=True)[:k]
        return [Hit(cid, chunks[cid].doc_id, fused[cid], chunks[cid].chunk) for cid in order]
