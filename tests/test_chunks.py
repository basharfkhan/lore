from datetime import date

from lore.data.reports import Report
from lore.ingest.chunks import (
    MAX_CHARS,
    _mask,
    boilerplate_lines,
    is_heading,
    llis_chunks,
    normalise_chars,
    paragraphs,
    report_chunks,
    split_long,
)

PROSE = (
    "The drogue parachute did not deploy because the G-switch sensors were installed in an "
    "inverted orientation, per an erroneous design, and could not sense deceleration. "
)


def test_hyphenation_is_rejoined():
    assert normalise_chars("spe\xad\ncific in-\nspection Mars-\nObserver") == (
        "specific inspection Mars-\nObserver"
    )


def test_page_variants_share_a_mask():
    keys = {_mask(s) for s in ["Page 32 Genesis Report", "Genesis Report Page E-4", "Page I Genesis Report"]}
    assert keys == {"genesis report"}


def test_boilerplate_needs_repetition_and_words():
    pages = [f"Genesis Report Page {i}\nBody text {i}.\nR3.3-{i}\n" for i in range(20)]
    drop = boilerplate_lines(pages)
    assert "genesis report" in drop
    assert not any(k.startswith("r") and len(k) < 4 for k in drop)


def test_headings():
    assert is_heading("4.1 SRC Avionics Unit Failure")
    assert is_heading("FINDINGS")
    assert not is_heading("The board found that the switch was inverted.")
    assert not is_heading("R3.3-1")


def test_paragraphs_rejoin_wrapped_lines_and_skip_page_numbers():
    text = "FINDINGS\nThe switch was\ninverted in the design.\n\n24\nA second paragraph here."
    assert list(paragraphs(text, set())) == [
        ("FINDINGS", True),
        ("The switch was inverted in the design.", False),
        ("A second paragraph here.", False),
    ]


def test_split_long_respects_limit():
    pieces = split_long(PROSE * 60)
    assert len(pieces) > 1
    assert all(len(p) <= MAX_CHARS for p in pieces)


def _lesson(**overrides):
    base = {
        "id": "llis-1",
        "lesson_number": 1,
        "title": "Inverted sensors",
        "date": "1999-02-01",
        "url": "https://llis.nasa.gov/lesson/1",
        "abstract": "",
        "driving_event": "A switch was installed backwards.",
        "lesson": "Polarity must be verified by test.",
        "recommendation": "Test end to end.",
    }
    return base | overrides


def test_short_lesson_is_one_chunk():
    [chunk] = llis_chunks([_lesson()])
    assert chunk.available_from == "1999-02-01"
    assert chunk.section is None
    assert "Driving event" in chunk.text and "Recommendation" in chunk.text
    assert chunk.context == "LLIS 1: Inverted sensors"


def test_long_lesson_is_split_with_sections():
    chunks = list(llis_chunks([_lesson(lesson=PROSE * 40)]))
    assert len(chunks) > 1
    assert all(c.char_count <= MAX_CHARS for c in chunks)
    assert all(c.section for c in chunks)


def test_report_chunks_carry_citation_and_cutoff_dates():
    report = Report(
        id="genesis",
        title="Genesis MIB Report",
        mission="Genesis",
        mishap_date=date(2004, 9, 8),
        report_date=date(2006, 6, 13),
        url="https://example.nasa.gov/genesis.pdf",
    )
    pages = [
        {"page": 7, "method": "text_layer", "text": "4.1 SRC Avionics\n" + PROSE * 5},
        {"page": 8, "method": "illegible", "text": ""},
    ]
    [chunk] = report_chunks(report, pages)
    assert chunk.available_from == "2006-06-13"
    assert chunk.mishap_date == "2004-09-08"
    assert chunk.url.endswith("#page=7")
    assert chunk.pages == [7]
    assert chunk.section == "4.1 SRC Avionics"
