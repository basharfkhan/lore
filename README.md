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

Data, OCR, chunking, a keyword baseline and a first draft of the historical eval (5 mishaps)
are done. Label review, embeddings and the agent are next.

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

## Chunking

`python -m lore.ingest.chunks` writes `data/processed/chunks.jsonl`: 6,486 chunks, 4,133 from
lessons and 2,353 from reports, median ~1,750 characters (~450 tokens), capped at 3,200.

- **Lessons stay whole when they fit.** A lesson is one argument (what happened, what it taught,
  what to do), so 1,508 of 2,117 are a single chunk; only the long ones are split, at their
  Driving event / Lesson / Recommendation boundaries.
- **Reports are streamed page by page.** Running headers and footers are detected per report
  and removed (including Genesis, which alternates its footer between facing pages), wrapped
  lines and hyphenation are rejoined, and paragraphs are packed into chunks that break at
  section headings. Chunks that are mostly non-words (OCR'd timing tables, contents pages) are
  dropped.
- **Every chunk carries `available_from`**, the date it first became readable (a lesson's date,
  a report's release date), plus the report's `mishap_date` and a citation URL with `#page=N`.
  The historical eval filters on `available_from`, so a pre-mortem for a mission can never
  retrieve the investigation written after it failed.

## Historical eval

Each case in [evals/cases.yaml](evals/cases.yaml) describes a system as it stood before a real
mishap, the way an engineer would ask for a pre-mortem, without naming the failure or its cause
(a test enforces this). The retriever sees only that description and only material available
before the mishap date. Labels in [evals/labels/](evals/labels/) grade each candidate document
2 (same failure mechanism), 1 (a contributing factor the board also cited) or 0, each with a
one-line reason.

Candidates are pooled from the case query plus hindsight queries written with knowledge of the
real root causes, and supplemented by direct searches. Labels are drafted, then human-reviewed
(`reviewed_by` in each file).

Keyword baseline (`python -m lore.eval.run`), draft labels:

| case | hit@10 (grade 2) | recall@10 | recall@20 | nDCG@10 | first grade-2 rank |
|---|---|---|---|---|---|
| Mars Climate Orbiter | 1 | 0.55 | 0.73 | 0.671 | 1 |
| Genesis | 1 | 0.14 | 0.24 | 0.397 | 1 |
| NOAA N-Prime | 1 | 0.16 | 0.21 | 0.528 | 1 |
| Columbia | 1 | 0.25 | 0.50 | 0.515 | 1 |
| Mars Polar Lander | 0 | 0.31 | 0.38 | 0.278 | not in top 100 |
| **mean** | **0.80** | **0.28** | **0.41** | **0.478** | |

These flatter BM25: the pool was built with BM25, so every document it ranks highly has been
judged, while documents only a semantic retriever would find have not been seen yet. The pool
will be widened with the embedding retriever before any comparison is claimed.

What the labelling found about the corpus itself:

- **Real precursors exist.** Voyager's 1977 lesson on thruster forces confusing navigation
  (LLIS 424) describes Mars Climate Orbiter's failure mode; three TOPEX/Poseidon handling
  incidents from 1992-93 foreshadow the NOAA N-Prime drop; Voyager's gyro-swap lesson warns
  against "spurious inputs triggering unwanted events", which is what shut down Mars Polar
  Lander's engines.
- **Mars Polar Lander is where keywords fail.** Its precursors talk about gyros, pyro events and
  star trackers, not touchdown sensors, so BM25 ranks none of them in the top 100. This is the
  case semantic retrieval has to win.
- **Some gaps are real.** Nothing in LLIS before 1999 concerns English/metric unit mismatches,
  and nothing before 2003 concerns external tank foam (only ice debris).
- **LLIS dates are not always trustworthy.** Two lessons were dated before the mishaps they
  describe (Genesis, WIRE). They are corrected in
  [configs/llis_date_overrides.yaml](configs/llis_date_overrides.yaml), and a test scans for more.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```
