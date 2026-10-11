import json
import math
import re

import pytest

from lore.eval.cases import POOL_DIR, load_cases
from lore.eval.metrics import first_rank, hit_at_k, ndcg_at_k, recall_at_k
from lore.ingest.chunks import OUT_PATH as CHUNKS_PATH

REL = {"a": 2, "b": 1, "c": 0}


def test_metrics():
    ranked = ["x", "b", "a", "y"]
    assert recall_at_k(ranked, REL, 2) == 0.5
    assert recall_at_k(ranked, REL, 3) == 1.0
    assert hit_at_k(ranked, REL, 2) == 0.0
    assert hit_at_k(ranked, REL, 3) == 1.0
    assert first_rank(ranked, REL) == 3
    assert ndcg_at_k(["a", "b"], REL, 2) == pytest.approx(1.0)
    assert 0 < ndcg_at_k(ranked, REL, 4) < 1
    assert math.isnan(recall_at_k(ranked, {"c": 0}, 5))


def test_case_descriptions_do_not_name_the_mishap():
    giveaways = {
        "mco": ["metric", "english units", "imperial"],
        "genesis": ["inverted", "upside", "backwards", "centrifuge"],
        "noaa_n_prime": ["bolts", "fell", "dropped"],
        "columbia": ["breakup", "broke up", "burn-through"],
        "mpl": ["spurious", "premature", "transient"],
    }
    for case in load_cases():
        words = giveaways.get(case.id, [])
        found = [w for w in words if re.search(rf"\b{re.escape(w)}\b", case.query, re.I)]
        assert not found, f"{case.id}: {found}"


@pytest.mark.skipif(not CHUNKS_PATH.exists(), reason="build chunks first")
def test_labels_point_at_real_documents_available_before_the_cutoff():
    available = {}
    with CHUNKS_PATH.open(encoding="utf-8") as f:
        for line in f:
            chunk = json.loads(line)
            available[chunk["doc_id"]] = chunk["available_from"]
    for case in load_cases():
        for doc_id in case.labels:
            assert doc_id in available, f"{case.id}: unknown document {doc_id}"
        for doc_id in case.relevant:
            assert available[doc_id] < case.cutoff_iso, f"{case.id}: {doc_id} is after the cutoff"


def test_every_pooled_candidate_is_judged():
    for case in load_cases():
        pool = POOL_DIR / f"{case.id}.jsonl"
        if not case.labels or not pool.exists():
            continue
        pooled = {
            json.loads(line)["doc_id"] for line in pool.read_text(encoding="utf-8").splitlines()
        }
        missing = sorted(pooled - set(case.labels))
        assert not missing, f"{case.id}: unjudged pooled documents {missing}"


def test_weighted_kappa_and_precision_recall():
    from lore.eval.judge import precision_recall, weighted_kappa

    perfect = [(0, 0), (1, 1), (2, 2), (0, 0)]
    assert weighted_kappa(perfect) == pytest.approx(1.0)
    assert weighted_kappa([(0, 2), (2, 0), (1, 1)]) < 0
    assert precision_recall([(2, 2), (0, 2), (2, 0)], 2) == (0.5, 0.5)


def test_names_in_guess_catches_hedged_recognition_only():
    from lore.eval.mine_cases import names_in_guess

    assert names_in_guess(["ULYSSES"], "Possibly Helios, Ulysses or ISEE-3") == ["ULYSSES"]
    assert names_in_guess(["UARS", "TOPEX"], "a horizon sensor on some LEO satellite") == []
    assert names_in_guess(["MER"], "a Mars rover such as Spirit (MER-A)") == ["MER"]


def test_leak_check_matches_whole_words_only():
    from lore.eval.mine_cases import leaked_terms, names_in_guess

    assert leaked_terms("after the spacecraft was shipped", ["AFT"]) == []
    assert leaked_terms("its AFT limits were narrow", ["AFT"]) == ["AFT"]
    assert names_in_guess(["ATLO", "MER"], "an ATLO campaign for a Mars rover (MER)") == ["MER"]
