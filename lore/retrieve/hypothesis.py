"""Hypothesis-driven retrieval: search once per generated failure hypothesis and fuse the results.

The original description is searched too, so documents that match the system directly are not
lost. The lists are interleaved round-robin (each hypothesis's best hit, then each one's second,
and so on) rather than fused by summed reciprocal rank: RRF rewards generic documents that sit
moderately high in many lists (fault protection, test guidelines) and buries the specific
precursor that a single hypothesis ranks first, which is exactly the document a pre-mortem is for.
On the eval, RRF cut hit@10 from 0.80 to 0.40 on the keyword base; round-robin restored it.
"""

from __future__ import annotations

from lore.agent.hypotheses import Hypothesis, generate
from lore.retrieve.bm25 import Hit
from lore.retrieve.hybrid import CANDIDATES


class HypothesisRetriever:
    def __init__(self, base, generator=generate):
        self.base = base
        self.generator = generator
        self.name = f"hypotheses+{base.name.split('-')[0]}"
        self.last_hypotheses: list[Hypothesis] = []

    def search(self, query: str, k: int = 20, before: str | None = None) -> list[Hit]:
        self.last_hypotheses = self.generator(query)
        queries = [query] + [h.search_query for h in self.last_hypotheses]
        lists = [self.base.search(q, max(k, CANDIDATES), before) for q in queries]
        out: list[Hit] = []
        seen: set[str] = set()
        for rank in range(max(len(hits) for hits in lists)):
            for hits in lists:
                if rank < len(hits) and hits[rank].chunk_id not in seen:
                    seen.add(hits[rank].chunk_id)
                    # Score encodes interleaved position so callers can still sort by it.
                    out.append(
                        Hit(hits[rank].chunk_id, hits[rank].doc_id, -len(out), hits[rank].chunk)
                    )
                    if len(out) == k:
                        return out
        return out
