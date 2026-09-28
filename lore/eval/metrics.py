"""Document-level ranking metrics for graded relevance (grades 0, 1, 2)."""

from __future__ import annotations

import math


def recall_at_k(ranked: list[str], relevant: dict[str, int], k: int, min_grade: int = 1) -> float:
    wanted = {d for d, g in relevant.items() if g >= min_grade}
    if not wanted:
        return float("nan")
    return len(wanted & set(ranked[:k])) / len(wanted)


def hit_at_k(ranked: list[str], relevant: dict[str, int], k: int, min_grade: int = 2) -> float:
    """1.0 if any document of at least ``min_grade`` is in the top k: 'did it raise the flag?'"""
    return float(any(relevant.get(d, 0) >= min_grade for d in ranked[:k]))


def ndcg_at_k(ranked: list[str], relevant: dict[str, int], k: int) -> float:
    def dcg(grades: list[int]) -> float:
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))

    ideal = dcg(sorted(relevant.values(), reverse=True)[:k])
    if ideal == 0:
        return float("nan")
    return dcg([relevant.get(d, 0) for d in ranked[:k]]) / ideal


def first_rank(ranked: list[str], relevant: dict[str, int], min_grade: int = 2) -> int | None:
    """1-based rank of the first document at ``min_grade`` or above, or None if absent."""
    for i, d in enumerate(ranked, 1):
        if relevant.get(d, 0) >= min_grade:
            return i
    return None
