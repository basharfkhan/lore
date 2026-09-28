"""Download the NASA Lessons Learned Information System and normalise it to JSONL.

The public site at llis.nasa.gov is a JavaScript app over an Elasticsearch index, and that
index answers anonymous searches. One request returns every lesson with full text, so there
is no scraping and no per-page crawling.

    python -m lore.data.llis            # fetch + normalise
    python -m lore.data.llis --offline  # re-normalise the saved raw dump
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import requests
import yaml

from lore.paths import CONFIG_DIR, PROCESSED_DIR, RAW_DIR
from lore.text import html_to_text

SEARCH_URL = "https://llis.nasa.gov/llis/lesson/_search"
LESSON_URL = "https://llis.nasa.gov/lesson/{number}"
# Comfortably above the 2,127 lessons present in September 2026. fetch() fails loudly if the
# index ever outgrows it rather than silently truncating.
MAX_LESSONS = 10_000

RAW_PATH = RAW_DIR / "llis" / "lessons_raw.json"
OVERRIDES_PATH = CONFIG_DIR / "llis_date_overrides.yaml"
OUT_PATH = PROCESSED_DIR / "llis.jsonl"

# (output field, source field) for the free-text parts of a lesson.
_TEXT_FIELDS = [
    ("abstract", "lessonAbstract"),
    ("driving_event", "description_event"),
    ("lesson", "lesson"),
    ("recommendation", "recommendation"),
    ("evidence", "evidence"),
]


def fetch(timeout: float = 120) -> dict:
    resp = requests.get(SEARCH_URL, params={"size": MAX_LESSONS}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    total = payload["hits"]["total"]
    got = len(payload["hits"]["hits"])
    if got != total:
        raise RuntimeError(f"LLIS returned {got} of {total} lessons; raise MAX_LESSONS")
    return payload


def _clean(value) -> str | None:
    if value is None:
        return None
    # Taxonomy fields arrive as {"name": ..., "category": ...}; the name is the useful part.
    if isinstance(value, dict):
        value = value.get("name")
        if value is None:
            return None
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if v)
    value = html_to_text(str(value))
    return value or None


def is_lesson(hit: dict) -> bool:
    """False for the stray documents the public index has accumulated.

    In September 2026 it held ten entries with ids like "_search?rnlybz.css" whose bodies are
    Elasticsearch queries: requests someone sent were stored as documents. They have no title
    or lesson number and must not reach the corpus.
    """
    src = hit["_source"]
    return str(src.get("lesson_number") or "").isdigit() and bool((src.get("title") or "").strip())


def normalise(hit: dict) -> dict:
    src = hit["_source"]
    number = src["lesson_number"]
    record = {
        "id": f"llis-{number}",
        "source": "llis",
        "lesson_number": int(number),
        "title": (src.get("title") or "").strip(),
        # lesson_date is the date the lesson was recorded, which is the right cutoff for the
        # historical eval: a lesson could not have warned anyone before it existed.
        "date": src.get("lesson_date") or None,
        "url": LESSON_URL.format(number=number),
        "organization": _clean(src.get("organization")),
        "mission_directorate": _clean(src.get("missionDirectorate")),
        "program_phase": _clean(src.get("programPhase")),
        "program_relation": _clean(src.get("programRelation")),
        "restriction": _clean(src.get("restriction")),
    }
    for out, field in _TEXT_FIELDS:
        record[out] = html_to_text(src.get(field))
    return record


def apply_date_overrides(records: list[dict], path: Path = OVERRIDES_PATH) -> int:
    """Replace impossible lesson dates; the original is kept as ``date_recorded``."""
    overrides = yaml.safe_load(path.read_text(encoding="utf-8"))["overrides"]
    by_number = {r["lesson_number"]: r for r in records}
    for item in overrides:
        record = by_number[item["lesson_number"]]
        if record["date"] != str(item["recorded"]):
            raise RuntimeError(
                f"LLIS {item['lesson_number']} is now dated {record['date']}, not "
                f"{item['recorded']}; re-check the override before applying it"
            )
        record["date_recorded"] = record["date"]
        record["date"] = str(item["date"])
    return len(overrides)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="reuse the saved raw dump")
    args = parser.parse_args()

    if args.offline:
        payload = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    else:
        payload = fetch()
        RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        RAW_PATH.write_text(json.dumps(payload), encoding="utf-8")
        stamp = {"fetched_at": datetime.now(UTC).isoformat(), "url": SEARCH_URL}
        (RAW_PATH.parent / "fetch.json").write_text(json.dumps(stamp, indent=2), encoding="utf-8")

    hits = payload["hits"]["hits"]
    lessons = [h for h in hits if is_lesson(h)]
    records = sorted((normalise(h) for h in lessons), key=lambda r: r["lesson_number"])
    if len({r["lesson_number"] for r in records}) != len(records):
        raise RuntimeError("duplicate lesson numbers in LLIS dump")
    corrected = apply_date_overrides(records)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    undated = sum(1 for r in records if not r["date"])
    print(
        f"{len(records)} lessons -> {OUT_PATH} "
        f"({len(hits) - len(lessons)} non-lesson entries dropped, {undated} undated, "
        f"{corrected} dates corrected)"
    )


if __name__ == "__main__":
    main()
