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
