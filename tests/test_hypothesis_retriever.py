from lore.agent.hypotheses import Hypothesis
from lore.retrieve.bm25 import Hit
from lore.retrieve.hypothesis import HypothesisRetriever


class Keyword:
    name = "hybrid-x"
    index = {
        "mars lander": ["mars-doc#0", "shuttle-landing#0"],
        "spurious signal": ["voyager-gyro#0", "viking-thrusters#0"],
        "transient at power-up": ["wire-pyro#0", "voyager-gyro#0"],
    }

    def search(self, query, k=20, before=None):
        return [Hit(c, c.split("#")[0], 1.0, {"id": c}) for c in self.index.get(query, [])[:k]]


def fake_generator(description):
    return [
        Hypothesis("f1", "m1", "software", "spurious signal"),
        Hypothesis("f2", "m2", "design", "transient at power-up"),
    ]


def test_hypotheses_surface_mechanism_matches_and_agreement_wins():
    retriever = HypothesisRetriever(Keyword(), generator=fake_generator)
    ranked = [h.chunk_id for h in retriever.search("mars lander", k=10)]
    assert ranked[0] == "voyager-gyro#0"  # found by both hypotheses
    assert {"mars-doc#0", "wire-pyro#0", "viking-thrusters#0"} <= set(ranked)
    assert len(retriever.last_hypotheses) == 2
