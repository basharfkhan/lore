from lore.retrieve.bm25 import Hit
from lore.retrieve.hybrid import HybridRetriever


class Fixed:
    def __init__(self, name, order, dates=None):
        self.name = name
        self.order = order
        self.dates = dates or {}

    def search(self, query, k=20, before=None):
        ids = [c for c in self.order if not before or self.dates.get(c, "1990") < before]
        return [Hit(c, c.split("#")[0], 1.0, {"id": c}) for c in ids[:k]]


def test_chunk_ranked_well_by_both_wins():
    keyword = Fixed("bm25", ["a#0", "b#0", "c#0"])
    dense = Fixed("dense", ["d#0", "b#0", "e#0"])
    ranked = [h.chunk_id for h in HybridRetriever(keyword, dense).search("q", k=5)]
    assert ranked[0] == "b#0"  # 2nd in both beats 1st in only one
    assert set(ranked) == {"a#0", "b#0", "c#0", "d#0", "e#0"}


def test_cutoff_is_passed_through():
    dates = {"new#0": "2005-01-01"}
    keyword = Fixed("bm25", ["new#0", "old#0"], dates)
    dense = Fixed("dense", ["new#0"], dates)
    ranked = [h.chunk_id for h in HybridRetriever(keyword, dense).search("q", before="2000-01-01")]
    assert ranked == ["old#0"]
