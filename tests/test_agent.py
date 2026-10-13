import pytest

from lore.agent.premortem import _cost, check_links
from lore.agent.tools import TOOLS, read_document, run_tool, search_archive
from lore.ingest.chunks import OUT_PATH as CHUNKS_PATH

needs_corpus = pytest.mark.skipif(not CHUNKS_PATH.exists(), reason="build chunks first")


def test_links_not_returned_by_a_tool_are_flagged():
    sources = {
        "https://llis.nasa.gov/lesson/267": "LLIS 267",
        "https://example.nasa.gov/report.pdf#page=12": "Report",
    }
    answer = (
        "See [LLIS 267](https://llis.nasa.gov/lesson/267), "
        "[the report](https://example.nasa.gov/report.pdf#page=40) and "
        "[an invented one](https://llis.nasa.gov/lesson/99999)."
    )
    assert check_links(answer, sources) == ["https://llis.nasa.gov/lesson/99999"]


def test_cost_counts_cache_reads_at_a_tenth():
    usage = {"input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000, "output_tokens": 0}
    assert _cost("claude-haiku-4-5", usage) == pytest.approx(1.10)


def test_tool_schemas_are_strict_objects():
    for tool in TOOLS:
        schema = tool["input_schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(schema["properties"])


@needs_corpus
def test_search_then_read_round_trip():
    results = search_archive("lifting fixture reused from another program")
    assert results and all({"id", "title", "url", "excerpt"} <= set(r) for r in results)
    document = read_document(results[0]["id"])
    assert document["url"] == results[0]["url"] and document["text"]
    reports = search_archive("foam debris strike", "reports")
    assert all(r["id"].startswith("report-") for r in reports)
    assert "#page=" in read_document(reports[0]["id"])["url"]


@needs_corpus
def test_unknown_ids_and_tools_return_errors_not_exceptions():
    assert "error" in read_document("llis-0")
    assert "error" in run_tool("delete_everything", {})


def test_follow_up_links_to_earlier_documents_are_supported():
    earlier = {"https://llis.nasa.gov/lesson/1196": "LLIS 1196"}
    assert check_links("As [LLIS 1196](https://llis.nasa.gov/lesson/1196) says.", earlier) == []


def test_process_chatter_before_the_report_is_removed():
    from lore.agent.premortem import strip_preamble

    report = "Two risks stand out.\n\n### 1. First risk\nDetails."
    for opener in [
        "Enough material gathered. Writing the pre-mortem now.",
        "Good, I have everything needed. Writing the report now.",
        "I now have enough to write the report.",
    ]:
        assert strip_preamble(f"{opener}\n\n{report}") == report


def test_real_opening_lines_are_kept():
    from lore.agent.premortem import strip_preamble

    for answer in [
        "Two risks stand out.\n\n### 1. First risk\nDetails.",
        "Here is [LLIS 267](https://llis.nasa.gov/lesson/267), the closest match.\n\nIt says more.",
        "I only do pre-mortems and questions about this archive.",
        "Your system has three linked single points of failure.\n\n### 1. Risk\nText.",
    ]:
        assert strip_preamble(answer) == answer


@needs_corpus
def test_cutoff_hides_later_documents_from_both_tools():
    late = search_archive("touchdown sensor transient signal engine shutdown")
    assert any(r["year"] >= "2000" for r in late)
    early = search_archive("touchdown sensor transient signal engine shutdown", before="1999-12-03")
    assert early and all(r["year"] <= "1999" for r in early)
    newer = next(r for r in late if r["year"] >= "2000")
    assert "error" in read_document(newer["id"], before="1999-12-03")
    assert "text" in read_document(newer["id"])
