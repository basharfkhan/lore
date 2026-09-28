"""Keyword baseline: Okapi BM25 over the chunks, with the date cutoff every retriever must honour.

This stands in for what an engineer has today (a keyword box on llis.nasa.gov), so every later
retriever is reported against it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from lore.paths import PROCESSED_DIR

CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"

# Deliberately small: BM25's IDF already discounts common words, this only removes the ones
# that would otherwise dominate short queries.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "which",
        "will",
        "with",
        "not",
        "no",
    }
)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    score: float
    chunk: dict


class BM25Retriever:
    name = "bm25"

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(f"{c['context']}\n{c['text']}") for c in chunks])

    @classmethod
    def from_file(cls, path: Path = CHUNKS_PATH) -> BM25Retriever:
        with path.open(encoding="utf-8") as f:
            return cls([json.loads(line) for line in f])

    def search(self, query: str, k: int = 20, before: str | None = None) -> list[Hit]:
        """Top-k chunks, keeping only those readable strictly before ``before`` (ISO date)."""
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
        hits = []
        for i in order:
            chunk = self.chunks[i]
            if before and not chunk["available_from"] < before:
                continue
            if scores[i] <= 0:
                break
            hits.append(Hit(chunk["id"], chunk["doc_id"], float(scores[i]), chunk))
            if len(hits) == k:
                break
        return hits


def unique_docs(hits: list[Hit], k: int) -> list[Hit]:
    """First hit per document, in rank order: evaluation is at document level."""
    seen, out = set(), []
    for hit in hits:
        if hit.doc_id not in seen:
            seen.add(hit.doc_id)
            out.append(hit)
            if len(out) == k:
                break
    return out
