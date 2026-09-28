# LORE: Lessons and Outcomes Retrieval Engine

Aviation became the safest way to travel because every accident investigation feeds
recommendations back to the people designing the next aircraft. Spaceflight has the same raw
material (decades of mishap boards and NASA's Lessons Learned Information System) but lessons
only prevent failures if engineers find them while they are still designing. NASA's Inspector
General has reported that the lessons system is underused.

LORE is a pre-mortem agent: describe a mission, subsystem or design decision, and it returns the
prior failures and lessons most relevant to it, with citations and the recommendation the
original investigators made.

The question the evaluation asks: **given a system as it stood before a real mishap, would LORE
have surfaced the warnings that already existed?** Retrieval is restricted to material dated
before the failure.

## Status

Milestone 0 (data) is done. Retrieval, the eval set and the agent are next.

## Data

| Source | Size | Rebuild |
|---|---|---|
| NASA Lessons Learned Information System | 2,117 lessons, 1972 to 2025 | `python -m lore.data.llis` |
| Mishap investigation reports ([configs/reports.yaml](configs/reports.yaml)) | 17 reports, Apollo 1 to Glory, ~2,000 pages | `python -m lore.data.reports` |

Both are public NASA material. Downloads land in `data/` (not tracked in git); the report
downloader verifies each file is a PDF and records its SHA-256 in `data/raw/reports/manifest.json`.

Notes from building it:

- LLIS is a JavaScript front end over an Elasticsearch index, and one anonymous search returns
  every lesson with full text. The index also holds ten stray documents that are stored search
  queries rather than lessons; `is_lesson` drops them.
- Lessons cluster in 1992 to 2011 and thin out after 2012, so the corpus says little about the
  commercial era.
- Every report has a text layer, but the older scans (Apollo 1 especially, where 39% of pages
  carry almost no text) will need OCR on their image-only pages.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```
