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

Milestone 0 (data) is done, and report text extraction with OCR is done. Chunking, retrieval,
the eval set and the agent are next.

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

## Reading the reports

`python -m lore.ingest.pages` writes one record per page to `data/processed/pages.jsonl`,
choosing per page between the PDF's own text and Tesseract OCR:

| Page kind | Example | Treatment |
|---|---|---|
| Born-digital | Genesis, MCO, DART | text layer as is |
| Old scan whose embedded OCR is one word per line | Apollo 1, Apollo 13, Mars Polar Lander, SOHO | whole report re-OCR'd at 300 dpi |
| Image-only page in a good document | NOAA N-Prime endorsement letter, where NASA's safety chief disputes some findings | that page OCR'd |

Of 1,925 pages, 1,193 use the text layer and 623 are OCR'd (mean word confidence 79 to 94 per
report). Pages that OCR poorly get Tesseract's orientation detection and a second pass, which
recovered 15 rotated pages, including the Mars Polar Lander touchdown-sensor logic at the heart
of that board's probable cause. 28 pages still below 50% confidence are photos read as text;
they are kept as `illegible` and never indexed.

OCR needs the Tesseract binary (`winget install UB-Mannheim.TesseractOCR` on Windows, or set
`TESSERACT_CMD`). Results are cached per page, so reruns take seconds.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```
