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

The data pipeline, four retrievers and the evaluation are done. On held-out cases the model
cannot recall, searching by generated failure hypotheses finds a direct precursor for 5 of 7
incidents, against 2 of 7 for keyword, dense or hybrid search (details under Evaluation). The
written pre-mortem report with citations and a web interface are not built yet.

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

## Evaluation

Every case describes a system as it stood before a real failure, the way an engineer would ask
for a pre-mortem, without naming the failure or its cause. The retriever sees only that
description and only material available before the failure date. A document counts as a
**direct precursor** when it describes the same failure mechanism, usually on unrelated hardware.

There are two sets of cases:

| Set | Cases | Used for |
|---|---|---|
| Dev ([evals/cases.yaml](evals/cases.yaml)) | 5 famous mishaps: Mars Climate Orbiter, Genesis, NOAA N-Prime, Columbia, Mars Polar Lander | building and debugging; every design choice was made here |
| Held-out ([evals/heldout/cases.yaml](evals/heldout/cases.yaml)) | 13 obscure incidents mined from LLIS | the reported result; nothing was tuned on them |

### Why the famous cases cannot be the headline

The hypothesis step uses an LLM, and the LLM knows spaceflight history.
`python -m lore.eval.contamination` asks the model whether it recognises each dev case. It
named all five missions with high confidence, down to the date of the N-Prime accident, and its
first hypothesis for Mars Polar Lander was the actual cause. Scores on those cases measure
memory as much as reasoning.

### Building cases the model cannot recall

`python -m lore.eval.mine_cases` takes the 56 LLIS lessons that narrate a dated incident and,
for each one:

1. rewrites it as an anonymised design-review summary that leaves out the detail that failed;
2. rejects it if a giveaway term the rewrite itself listed appears in the description;
3. runs the contamination probe and rejects it if the model names the real mission, even as a
   hedged guess, or recalls what actually happened;
4. asks the model blind for the single most likely failure, and marks the case **easy** if that
   guess is the real mechanism and **hard** otherwise.

13 cases survive (8 hard, 5 easy). Most of the 43 rejections are incidents from Mars Observer,
Cassini, Mars Global Surveyor, Deep Space 1 and the Mars rovers, which the model recognises
from an anonymised paragraph. The retrieval cutoff for each case is 1 January of the event year.

### Grading

The first labels were free-form grades of 2, 1 or 0. That scale did not hold up: on the same
lessons the draft labels, an LLM judge and the human reviewer gave three different grades, and
the judge agreed with the drafts at a weighted kappa of only 0.57. Many of the drafts were the
ones at fault, graded from short excerpts.

Each mishap's cause is now split into two parts ([evals/criteria.yaml](evals/criteria.yaml)).
For NOAA N-Prime: (A) equipment left in a changed state by earlier work that was not recorded,
and (B) the next team operating it without checking. A document about both parts is a 2, about
one is a 1, about neither is a 0.

- The reviewer answered the two questions for the 22 documents where the judge and the drafts
  disagreed about a direct precursor
  ([evals/review/adjudication_checklist.md](evals/review/adjudication_checklist.md)).
- The judge, asked the same two questions, agrees with those answers at weighted kappa 0.78,
  with precision and recall of 0.80 on direct precursors, and is never more than one grade away.
  These 22 are the disputed documents, so they are harder than a random sample.
- The judge grades everything else, and the human answers override it where they exist.

Limits: the reviewer is one person, the judge is the same model family that generates the
hypotheses, and the two-part criteria for held-out cases are generated from each hidden
mechanism rather than hand-written. Columbia has no direct precursor under this rule: before
2003 the archive has a lesson about ascent debris and the Challenger report about accepting a
recurring problem, but nothing about both.

### Held-out results

`python -m lore.eval.heldout` pools the top 30 documents from every retriever for each case,
plus results for hindsight queries, and has the judge grade the whole pool, so no retriever is
penalised for documents nobody graded. Of the 13 cases, 7 have a direct precursor somewhere in
the archive. For those 7:

| Retriever | direct precursor in top 30 | recall@30 (grade 1 or 2) | hard cases (4): precursor in top 30 |
|---|---|---|---|
| BM25 (keyword) | 2 of 7 | 0.23 | 0 of 4 |
| Dense (bge-base-en-v1.5) | 2 of 7 | 0.22 | 1 of 4 |
| Hybrid (reciprocal rank fusion) | 2 of 7 | 0.25 | 1 of 4 |
| Hypotheses + BM25 | **5 of 7** | 0.31 | **3 of 4** |
| Hypotheses + hybrid | **5 of 7** | **0.34** | **3 of 4** |

Searching by generated failure hypotheses found a direct precursor in three hard cases where
keyword, dense and hybrid search all found none, and lost one case the other way. Seven cases
are too few for this to be statistically secure; it is a consistent direction on cases the model
cannot have memorised. In the top 10 no method does well (at most 2 of 7), because ten
hypotheses share the list and each gets about one slot. A pre-mortem report would show a few
precursors under each hypothesis, which is why the comparison is made at 30.

The other 6 held-out cases have no direct precursor in the archive at all. For those incidents
no search method could have surfaced a warning, because none had been written down.

### What the dev cases taught

- **Dense retrieval matches topic, not failure mechanism.** Asked about a Mars lander it
  returns Mars documents and Shuttle landing lessons. Mars Polar Lander's precursors are about
  Voyager's gyros, a Galileo reset circuit and Viking's thrusters firing on the launch pad.
- **Fusing hypothesis results by summed rank hides the answer.** Reciprocal rank fusion over
  eleven result lists favours generic documents that sit moderately high in many of them.
  Interleaving the lists round-robin keeps each hypothesis's best hit.
- **Some gaps in the archive are real.** Nothing in LLIS before 1999 concerns English/metric
  unit mismatches, and nothing before 2003 concerns external tank foam.
- **LLIS dates are not always right.** Two lessons were dated before the mishaps they describe
  (Genesis, WIRE). They are corrected in
  [configs/llis_date_overrides.yaml](configs/llis_date_overrides.yaml), and a test scans for more.

Dev-case scores are in [evals/results/](evals/results/). They are not reported here because of
the contamination above.

### Cost

The LLM steps (hypotheses, case mining, contamination probes, judging) took about 540 calls to
`claude-opus-5`, roughly $26 at list prices. Responses are cached on disk by request, so reruns
are free.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,embed]"
.venv/Scripts/python -m pytest
```

Dense retrieval downloads the embedding model on first use. The LLM steps need an Anthropic API
key in `.env` (see `.env.example`).
