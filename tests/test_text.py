from lore.data.llis import is_lesson, normalise
from lore.text import html_to_text


def test_paragraphs_and_entities():
    html = "<p> Failure to consider <u>fatigue</u> &amp; loads.</p> \n<p>Second&nbsp;para.</p>"
    assert html_to_text(html) == "Failure to consider fatigue & loads.\n\nSecond para."


def test_list_items_become_bullets():
    assert html_to_text("<ul><li>one</li><li>two</li></ul>") == "- one\n\n- two"


def test_empty_markers_are_blank():
    for marker in [None, "", "None", "<p> N/A</p>", "<p>TBD</p>"]:
        assert html_to_text(marker) == ""


def test_normalise_llis_hit():
    hit = {
        "_id": "696",
        "_source": {
            "lesson_number": 696,
            "title": " Fatigue Reliability ",
            "lesson_date": "1999-01-31",
            "lesson": "<p>Consider fatigue.</p>",
            "recommendation": "<p>Use spectral methods.</p>",
            "evidence": "None",
            "programPhase": "None",
            "organization": {"abr": "jsc", "name": "JSC", "category": "NASA Centers"},
            "missionDirectorate": {"name": ["Science", "Exploration"], "category": "x"},
        },
    }
    record = normalise(hit)
    assert record["id"] == "llis-696"
    assert record["title"] == "Fatigue Reliability"
    assert record["date"] == "1999-01-31"
    assert record["url"] == "https://llis.nasa.gov/lesson/696"
    assert record["lesson"] == "Consider fatigue."
    assert record["evidence"] == ""
    assert record["program_phase"] is None
    assert record["organization"] == "JSC"
    assert record["mission_directorate"] == "Science, Exploration"


def test_stray_query_documents_are_not_lessons():
    stray = {"_id": "_search?rnlybz.css", "_source": {"query": {"more_like_this": {}}}}
    real = {"_id": "696", "_source": {"lesson_number": 696, "title": "Fatigue"}}
    assert not is_lesson(stray)
    assert is_lesson(real)
