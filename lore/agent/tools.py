"""The tools the pre-mortem agent can call: search the archive and read a document in full.

Search is BM25 only. On the held-out evaluation, hypothesis-driven search scored the same over
BM25 as over the hybrid retriever (a direct precursor in the top 30 for 5 of 7 incidents), and
BM25 needs no embedding model, so the deployed service stays small.
"""

from __future__ import annotations

import json
from functools import lru_cache

from lore.data.llis import OUT_PATH as LLIS_PATH
from lore.retrieve.bm25 import BM25Retriever, unique_docs

MAX_RESULTS = 8
EXCERPT_CHARS = 320
DOCUMENT_CHARS = 6000

TOOLS = [
    {
        "name": "search_archive",
        "description": (
            "Search NASA's Lessons Learned Information System (2,117 lessons, 1972-2025) and 17 "
            "mishap investigation reports (Apollo 1 to Glory) by keyword. Returns the best "
            "matching documents with an id, title, year, source link and a short excerpt. "
            "Search for a failure mechanism in generic engineering terms (for example "
            "'spurious sensor signal latched by software during deployment'), not for the "
            "user's mission or hardware by name: the most useful precedent is usually about "
            "different hardware. Run a separate search for each distinct failure mode."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords describing one failure mode."},
                "source": {
                    "type": "string",
                    "enum": ["all", "lessons", "reports"],
                    "description": "Restrict to lessons or to mishap reports. Default all.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_document",
        "description": (
            "Read one search result in full: the whole lesson (what happened, the lesson, the "
            "recommendation), or for a mishap report the matching passage and the one after it. "
            "Read a document before citing it, so the precedent and the investigators' "
            "recommendation are quoted accurately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The id from a search_archive result."}
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    },
]


@lru_cache(maxsize=1)
def _retriever() -> BM25Retriever:
    return BM25Retriever.from_file()


@lru_cache(maxsize=1)
def _lessons() -> dict[str, dict]:
    with LLIS_PATH.open(encoding="utf-8") as f:
        return {(x := json.loads(line))["id"]: x for line in f}


def search_archive(query: str, source: str = "all") -> list[dict]:
    hits = _retriever().search(query, 300)
    if source != "all":
        wanted = "llis" if source == "lessons" else "report"
        hits = [h for h in hits if h.chunk["source"] == wanted]
    results = []
    for hit in unique_docs(hits, MAX_RESULTS):
        c = hit.chunk
        results.append(
            {
                # Lessons are read whole, so their id is the lesson; a report id names a passage.
                "id": c["doc_id"] if c["source"] == "llis" else c["id"],
                "title": c["doc_title"],
                "year": c["available_from"][:4],
                "url": c["url"],
                "excerpt": " ".join(c["text"].split())[:EXCERPT_CHARS],
            }
        )
    return results


def read_document(id: str) -> dict:
    lesson = _lessons().get(id)
    if lesson:
        parts = [
            ("What happened", lesson["driving_event"]),
            ("Lesson", lesson["lesson"]),
            ("Recommendation", lesson["recommendation"]),
        ]
        text = "\n\n".join(f"{label}:\n{body}" for label, body in parts if body)
        return {
            "id": id,
            "title": f"LLIS {lesson['lesson_number']}: {lesson['title']}",
            "date": lesson["date"],
            "url": lesson["url"],
            "text": text[:DOCUMENT_CHARS],
        }
    chunks = _retriever().chunks
    index = next((i for i, c in enumerate(chunks) if c["id"] == id), None)
    if index is None:
        return {"error": f"No document with id {id!r}. Use an id returned by search_archive."}
    chunk = chunks[index]
    passages = [chunk["text"]]
    if index + 1 < len(chunks) and chunks[index + 1]["doc_id"] == chunk["doc_id"]:
        passages.append(chunks[index + 1]["text"])
    return {
        "id": id,
        "title": chunk["doc_title"],
        "section": chunk["section"],
        "pages": chunk["pages"],
        "date": chunk["available_from"],
        "url": chunk["url"],
        "text": "\n\n".join(passages)[:DOCUMENT_CHARS],
    }


def run_tool(name: str, arguments: dict) -> dict | list:
    if name == "search_archive":
        return search_archive(arguments["query"], arguments.get("source", "all"))
    if name == "read_document":
        return read_document(arguments["id"])
    return {"error": f"Unknown tool {name!r}."}
