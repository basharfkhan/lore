"""Hypothesis-driven retrieval: search once per generated failure hypothesis and fuse the results.

The original description is searched too, so documents that match the system directly are not
lost; reciprocal rank fusion then favours documents that several hypotheses agree on.
"""

from __future__ import annotations

from lore.agent.hypotheses import Hypothesis, generate
from lore.retrieve.bm25 import Hit
from lore.retrieve.hybrid import CANDIDATES, RRF_K


class HypothesisRetriever:
    def __init__(self, base, generator=generate, k: int = RRF_K):
        self.base = base
        self.generator = generator
        self.k = k
        self.name = f"hypotheses+{base.name.split('-')[0]}"
        self.last_hypotheses: list[Hypothesis] = []

    def search(self, query: str, k: int = 20, before: str | None = None) -> list[Hit]:
        self.last_hypotheses = self.generator(query)
        queries = [query] + [h.search_query for h in self.last_hypotheses]
        fused: dict[str, float] = {}
        chunks: dict[str, Hit] = {}
        for q in queries:
            for rank, hit in enumerate(self.base.search(q, max(k, CANDIDATES), before), 1):
                fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (self.k + rank)
                chunks.setdefault(hit.chunk_id, hit)
        order = sorted(fused, key=fused.__getitem__, reverse=True)[:k]
        return [Hit(cid, chunks[cid].doc_id, fused[cid], chunks[cid].chunk) for cid in order]
