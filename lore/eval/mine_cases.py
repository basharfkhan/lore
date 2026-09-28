"""Build held-out eval cases from obscure LLIS incidents, keeping only ones the model can't recall.

The five hand-written cases are famous, and the contamination probe shows the model remembers
how each ended, so they measure memory as much as reasoning. LLIS is full of small incidents
nobody has heard of. For each dated incident lesson this:

1. asks Claude to rewrite the incident as a pre-mortem request: the system or operation as it
   stood before the event, anonymised, with nothing that reveals what went wrong;
2. checks the rewrite mechanically for giveaway terms the same call listed;
3. runs the contamination probe on the rewrite and keeps the case only if the model does not
   recognise it (confidence none or low).

The retrieval cutoff is 1 January of the event year, so nothing written that year can leak in,
including the source lesson itself.

    python -m lore.eval.mine_cases              # writes evals/heldout/cases.yaml
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

import anthropic
import yaml

from lore.data.llis import OUT_PATH as LLIS_PATH
from lore.eval.cases import EVAL_DIR
from lore.eval.contamination import SCHEMA as PROBE_SCHEMA
from lore.eval.contamination import SYSTEM as PROBE_SYSTEM
from lore.llm import MODEL, RefusalError, TruncatedError, json_call

HELDOUT_DIR = EVAL_DIR / "heldout"
WORKERS = 3  # independent requests; the SDK retries on 429/529 with backoff
EARLIEST_YEAR = 1993  # LLIS is thin before 1992, so earlier cases would have no precursors

# Missions already covered by the dev cases, or famous enough to be recognised on sight.
_FAMOUS = re.compile(
    r"Mars Climate|Mars Polar|Genesis|Columbia|Challenger|51-L|NOAA|Apollo|Hubble|WIRE|"
    r"Wide-Field|SOHO|Lewis|CONTOUR|DART|Glory|Orbiting Carbon|Deep Space 2|STS-107",
    re.IGNORECASE,
)
_INCIDENT = re.compile(
    r"\b(anomal|mishap|failure|failed|incident|close call|damage|loss|lost|drop|fire|"
    r"explosion|leak|malfunction|scrub)",
    re.IGNORECASE,
)
_GUIDELINE = re.compile(
    r"Reliability (Preferred )?Practice|Technical Memorandum 4322|This Lesson Learned is based on",
    re.IGNORECASE,
)
_TITLE_YEAR = re.compile(r"\((?:~|ca\.?\s*)?((?:19|20)\d\d)(?:[-/]\d+)?\)")

REWRITE_SYSTEM = """\
You turn a NASA lessons-learned incident report into a test case for a pre-mortem tool.

First decide whether the report describes one specific incident (something that happened to \
particular hardware, software, a test or an operation) rather than general guidance.

If it does, write the pre-mortem request an engineer would have written BEFORE the incident: \
a description of the system or operation as it stood, how it was designed, built, verified or \
run, and the constraints it was under, in 80 to 150 words. Rules for that description:
- Never state or hint at what went wrong, its cause, or the corrective action.
- Include only facts that were true beforehand; a design choice that later proved to be the \
cause may appear as a neutral fact only if the team would naturally have mentioned it.
- Anonymise: no mission, spacecraft, program, contractor or centre names, and no dates. Use \
generic descriptions such as "an outer-planet orbiter" or "a vacuum test facility".

Also give: the failure mechanism in one sentence (kept hidden from the tool, used for grading), \
three to five short generic search queries a reliability engineer who knew the cause would use \
to find earlier lessons about the same mechanism, and the words or phrases that would give the \
cause away if they appeared in the description."""

REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_specific_incident": {"type": "boolean"},
        "description": {"type": "string"},
        "failure_mechanism": {"type": "string"},
        "hindsight_queries": {"type": "array", "items": {"type": "string"}},
        "giveaway_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "is_specific_incident",
        "description",
        "failure_mechanism",
        "hindsight_queries",
        "giveaway_terms",
    ],
    "additionalProperties": False,
}


BLIND_SYSTEM = """\
You are a spacecraft reliability engineer. Read the system description and state the single \
most likely way it fails, in one sentence naming the specific mechanism."""

BLIND_SCHEMA = {
    "type": "object",
    "properties": {"failure": {"type": "string"}},
    "required": ["failure"],
    "additionalProperties": False,
}

MATCH_SYSTEM = """\
Decide whether a predicted failure names the same failure mechanism as the actual one. Same \
mechanism means the same physical or procedural cause, not merely the same subsystem or \
symptom."""

MATCH_SCHEMA = {
    "type": "object",
    "properties": {"same_mechanism": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["same_mechanism", "reason"],
    "additionalProperties": False,
}

# Organisations and generic words that appear in source reports and guesses without identifying
# the mission.
_NAME_STOPLIST = {
    "nasa", "jpl", "esa", "gsfc", "ksc", "jsc", "msfc", "arc", "the", "this", "during", "after",
    "following", "mission", "spacecraft", "flight", "test", "project", "program", "earth", "mars",
    "sun", "solar", "space", "shuttle", "orbiter", "lesson", "lessons", "learned", "however",
}  # fmt: skip


def names_in_guess(source: str, guess: str) -> list[str]:
    """Proper names and acronyms from the source report that also appear in the probe's guess."""
    acronyms = set(re.findall(r"\b[A-Z][A-Z0-9-]{2,}\b", source))
    # A capitalised word is a name only if it never appears lowercase: "Sensor" in "Earth
    # Sensor Assembly" is an ordinary word the guess also uses ("horizon sensor").
    text = f"{source} {guess}"
    titled = {
        w
        for w in re.findall(r"\b[A-Z][a-z]{3,}\b", source)
        if not re.search(rf"\b{w.lower()}\b", text)
    }
    names = acronyms | titled
    guess_lower = guess.lower()
    return sorted(
        n
        for n in names
        if n.lower() not in _NAME_STOPLIST
        and re.search(rf"\b{re.escape(n.lower())}\b", guess_lower)
    )


def candidates(lessons: list[dict]) -> list[tuple[int, dict]]:
    out, seen_titles = [], set()
    for lesson in lessons:
        match = _TITLE_YEAR.search(lesson["title"])
        if not match or int(match.group(1)) < EARLIEST_YEAR:
            continue
        text = f"{lesson['title']} {lesson['driving_event']}"
        if _FAMOUS.search(text) or _GUIDELINE.search(lesson["driving_event"]):
            continue
        if not _INCIDENT.search(text) or len(lesson["driving_event"]) < 400:
            continue
        # Some incidents were entered twice ("Test 11: DS1 Ion Engine Shut-Down Anomaly").
        core = re.sub(r"^Test \d+:\s*|\s*-\s*Test \d+$", "", lesson["title"]).lower()
        if core in seen_titles:
            continue
        seen_titles.add(core)
        out.append((int(match.group(1)), lesson))
    return out


def leaked_terms(description: str, terms: list[str]) -> list[str]:
    text = description.lower()
    return [t for t in terms if t.strip() and t.lower() in text]


def build_case(year: int, lesson: dict) -> tuple[str, dict]:
    """Rewrite, leak-check and probe one incident; returns ("keep" | "reject", record)."""
    source = (
        f"Title: {lesson['title']}\n\nDriving event:\n{lesson['driving_event']}\n\n"
        f"Lesson:\n{lesson['lesson']}\n\nRecommendation:\n{lesson['recommendation']}"
    )
    case_id = f"llis{lesson['lesson_number']}"
    rewrite = json_call(REWRITE_SYSTEM, source, REWRITE_SCHEMA, max_tokens=8000)
    if not rewrite["is_specific_incident"]:
        return "reject", {"id": case_id, "reason": "not a specific incident"}
    leaks = leaked_terms(rewrite["description"], rewrite["giveaway_terms"])
    if leaks:
        return "reject", {"id": case_id, "reason": f"description leaks {leaks}"}
    probe = json_call(PROBE_SYSTEM, rewrite["description"], PROBE_SCHEMA, max_tokens=4000)
    if probe["recognised"] and probe["confidence"] in ("medium", "high"):
        return "reject", {"id": case_id, "reason": f"recognised as {probe['mission_guess']!r}"}
    # A hedged "not sure, possibly Ulysses" that names the real mission is still recognition.
    named = names_in_guess(f"{lesson['title']} {lesson['driving_event']}", probe["mission_guess"])
    if named:
        return "reject", {"id": case_id, "reason": f"probe named the real mission {named}"}
    blind = json_call(BLIND_SYSTEM, rewrite["description"], BLIND_SCHEMA, max_tokens=4000)
    match = json_call(
        MATCH_SYSTEM,
        f"Actual mechanism:\n{rewrite['failure_mechanism']}\n\nPrediction:\n{blind['failure']}",
        MATCH_SCHEMA,
        max_tokens=2000,
    )
    return "keep", {
        "id": case_id,
        "source_lesson": lesson["id"],
        "source_title": lesson["title"],
        "cutoff": f"{year}-01-01",
        "query": rewrite["description"],
        "failure_mechanism": rewrite["failure_mechanism"],
        "hindsight_queries": rewrite["hindsight_queries"],
        # "easy" when a single blind guess already names the mechanism: the description gives
        # it away, or the failure is the obvious one. Results are reported separately.
        "difficulty": "easy" if match["same_mechanism"] else "hard",
        "blind_guess": blind["failure"],
        "contamination": {
            "recognised": probe["recognised"],
            "confidence": probe["confidence"],
            "guess": probe["mission_guess"],
        },
    }


def main() -> None:
    with LLIS_PATH.open(encoding="utf-8") as f:
        lessons = [json.loads(line) for line in f]

    def attempt(candidate: tuple[int, dict]) -> tuple[str, dict]:
        # A persistent API error on one case must not sink the batch; rerunning picks the
        # failed cases up again, and finished calls come from the cache.
        try:
            return build_case(*candidate)
        except (anthropic.APIError, RefusalError, TruncatedError) as exc:
            return "error", {"id": f"llis{candidate[1]['lesson_number']}", "reason": str(exc)}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(attempt, candidates(lessons)))
    kept = [case for status, case in outcomes if status == "keep"]
    rejected = [case for status, case in outcomes if status == "reject"]
    errors = [case for status, case in outcomes if status == "error"]
    if errors:
        print(f"{len(errors)} cases hit API errors; rerun to retry them:")
        for e in errors:
            print(f"  error   {e['id']:9s} {e['reason'][:80]}")
    for case in kept:
        print(f"  keep    {case['id']:9s} {case['cutoff'][:4]}  {case['source_title'][:60]}")

    for r in rejected:
        print(f"  reject  {r['id']:9s} {r['reason'][:90]}")
    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    header = (
        "# Held-out cases mined from obscure LLIS incidents by lore/eval/mine_cases.py.\n"
        f"# Rewritten and contamination-probed with {MODEL}; only unrecognised cases kept.\n"
        "# Never tune on these: they exist to test a design fixed on the dev cases.\n"
    )
    body = yaml.safe_dump(
        {"cases": kept, "rejected": rejected}, sort_keys=False, allow_unicode=True, width=100
    )
    (HELDOUT_DIR / "cases.yaml").write_text(header + body, encoding="utf-8")
    print(f"\n{len(kept)} kept, {len(rejected)} rejected -> {HELDOUT_DIR / 'cases.yaml'}")


if __name__ == "__main__":
    main()
