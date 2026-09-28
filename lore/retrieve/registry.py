"""Build retrievers by name so the eval and pooling scripts share one definition of each."""

from __future__ import annotations

import json

from lore.retrieve.bm25 import CHUNKS_PATH, BM25Retriever


def build_retrievers(names: list[str]) -> list:
    with CHUNKS_PATH.open(encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    built: dict[str, object] = {}

    def get(name: str):
        if name not in built:
            if name == "bm25":
                built[name] = BM25Retriever(chunks)
            elif name == "dense":
                from lore.retrieve.dense import DenseRetriever

                built[name] = DenseRetriever(chunks)
            elif name == "hybrid":
                from lore.retrieve.hybrid import HybridRetriever

                built[name] = HybridRetriever(get("bm25"), get("dense"))
            elif name == "hypotheses":
                from lore.retrieve.hypothesis import HypothesisRetriever

                built[name] = HypothesisRetriever(get("hybrid"))
            else:
                raise ValueError(f"unknown retriever {name!r}")
        return built[name]

    return [get(name) for name in names]
