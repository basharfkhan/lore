"""Do the reports say what their sources say?

The link audit in the app proves a cited document was retrieved. It does not prove the sentence
next to the link is true to that document. This evaluation checks that.

1. The agent (the model the live site uses) writes a pre-mortem for each held-out brief, with
   its tools limited to documents written before that incident.
2. Each report is split into its numbered risks. For every risk a different, stronger model
   reads the cited documents and judges three things separately: is what the report says
   happened supported, is the recommendation it attributes to the investigators supported, and
   does the "Check" line follow from the documents or add something of its own.
3. Because the briefs are the held-out incidents, the same runs show how often the finished
   report cites a direct precursor, the end-to-end version of the retrieval result.

Agent runs are saved per case and judge calls are cached, so a rerun only pays for what is
missing.

    python -m lore.eval.faithfulness
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

import anthropic

from lore.agent.premortem import run as run_agent
from lore.agent.tools import read_document
from lore.eval.cases import EVAL_DIR
from lore.eval.heldout import load_heldout
from lore.llm import MODEL as JUDGE_MODEL
from lore.llm import RefusalError, TruncatedError, json_call

RUNS_DIR = EVAL_DIR / "faithfulness" / "runs"
RESULTS_PATH = EVAL_DIR / "results" / "faithfulness.json"
HELDOUT_RESULTS = EVAL_DIR / "results" / "heldout.json"
WORKERS = 3

_RISK_HEADING = re.compile(r"^#{1,4}[ \t]*(\d+)\.[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_BOLD_HEADING = re.compile(r"^[ \t]*\*\*(\d+\.\s[^\n]+?)\*\*[ \t]*$", re.MULTILINE)
_CHECK = re.compile(r"(?:^|\s)(?:\*\*|__)?Check:(?:\*\*|__)?\s*", re.MULTILINE)
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

JUDGE_SYSTEM = """\
You verify a pre-mortem report against the documents it cites. The report was written by an AI \
agent from NASA lessons-learned records. For each numbered risk you are given the risk's text, \
its "Check" line and the full text of every document it cites.

Judge three things for each risk, using only the cited documents:

precedent - the statements about what happened in the past (what failed, to what, why).
  supported: every such statement is stated in or directly follows from the cited documents.
  partly: the gist is right but a specific detail (a number, a cause, a name, a sequence) is \
not in the documents or is distorted.
  unsupported: the documents do not say this, or say something different.

recommendation - what the report says the investigators recommended or concluded.
  supported / partly / unsupported as above; none if the risk attributes no recommendation.

check - the "Check" line, which applies the lesson to the user's own system.
  grounded: it applies a recommendation the documents actually make.
  extends: reasonable, but it adds a specific step, threshold or requirement the documents do \
not contain.
  ungrounded: it has no basis in the cited documents.
  none: the risk has no Check line.

Ignore sentences that only describe the user's system or speculate about it; those are not \
claims about the sources. Be exact: if a figure or a quoted phrase is not in the document text, \
that is at best "partly". In `problem`, quote the specific statement that is not supported, or \
leave it empty."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "precedent": {"type": "string", "enum": ["supported", "partly", "unsupported"]},
                    "recommendation": {
                        "type": "string",
                        "enum": ["supported", "partly", "unsupported", "none"],
                    },
                    "check": {
                        "type": "string",
                        "enum": ["grounded", "extends", "ungrounded", "none"],
                    },
                    "problem": {"type": "string"},
                },
                "required": ["number", "precedent", "recommendation", "check", "problem"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["risks"],
    "additionalProperties": False,
}


@dataclass
class Risk:
    number: int
    title: str
    body: str
    check: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (title, url)


def parse_risks(answer: str) -> list[Risk]:
    """Split a report into its numbered risks, whichever heading style the model used."""
    text = _BOLD_HEADING.sub(lambda m: f"### {m.group(1)}", answer)
    headings = list(_RISK_HEADING.finditer(text))
    risks = []
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        section = text[heading.end() : end].strip()
        parts = _CHECK.split(section, maxsplit=1)
        body = parts[0].strip()
        check = parts[1].strip() if len(parts) > 1 else ""
        # A closing disclaimer after the last Check line is not part of the check.
        check = re.split(
            r"\n\s*(?:---+|\*[^*\n]*research aid[^*\n]*\*|This is a research aid)", check
        )[0].strip()
        risks.append(
            Risk(
                number=int(heading.group(1)),
                title=heading.group(2).strip(" *"),
                body=body,
                check=check,
                links=_LINK.findall(section),
            )
        )
    return risks


def agent_run(case) -> dict:
    """The agent's report for one held-out brief, saved so it is only ever paid for once."""
    path = RUNS_DIR / f"{case.id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = run_agent(case.query, before=case.cutoff_iso)
    record = {
        "case": case.id,
        "cutoff": case.cutoff_iso,
        "model": result.model,
        "answer": result.answer,
        "steps": result.steps,
        "source_ids": result.source_ids,
        "unsupported_links": result.unsupported_links,
        "cost_usd": result.cost_usd,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def judge_report(case, record: dict) -> list[dict]:
    risks = parse_risks(record["answer"])
    ids = record["source_ids"]
    documents: dict[str, dict] = {}
    blocks = []
    for risk in risks:
        cited = []
        for _, url in risk.links:
            doc_id = ids.get(url) or ids.get(url.split("#")[0])
            if doc_id and doc_id not in documents:
                documents[doc_id] = read_document(doc_id, before=case.cutoff_iso)
            if doc_id:
                cited.append(doc_id)
        cites = ", ".join(dict.fromkeys(cited)) or "nothing"
        blocks.append(
            f'<risk number="{risk.number}" cites="{cites}">\n'
            f"{risk.title}\n\n{risk.body}\n\nCheck: {risk.check or '(none)'}\n</risk>"
        )

    def document_block(doc_id: str, doc: dict) -> str:
        body = doc.get("text", doc.get("error", ""))
        # The agent's tools return the date the document was recorded, so the judge sees it too.
        recorded = f"Date recorded: {doc['date']}\n" if doc.get("date") else ""
        return f'<document id="{doc_id}">\n{doc.get("title", "")}\n{recorded}\n{body}\n</document>'

    docs = "\n\n".join(document_block(doc_id, d) for doc_id, d in documents.items())
    verdicts = {}
    if risks:
        user = "Risks:\n\n" + "\n\n".join(blocks) + "\n\nCited documents:\n\n" + docs
        out = json_call(JUDGE_SYSTEM, user, JUDGE_SCHEMA, max_tokens=8000)
        verdicts = {v["number"]: v for v in out["risks"]}

    rows = []
    for risk in risks:
        cited = [ids.get(u) or ids.get(u.split("#")[0]) for _, u in risk.links]
        v = verdicts.get(risk.number, {})
        rows.append(
            {
                **asdict(risk),
                "cited_ids": [c for c in dict.fromkeys(cited) if c],
                "precedent": v.get("precedent", "unjudged") if cited else "uncited",
                "recommendation": v.get("recommendation", "unjudged") if cited else "uncited",
                "check": v.get("check", "unjudged"),
                "problem": v.get("problem", ""),
            }
        )
    return rows


def share(counter: Counter, key: str) -> float:
    total = sum(counter.values())
    return counter[key] / total if total else float("nan")


def main() -> None:
    cases = load_heldout()

    def work(case):
        try:
            record = agent_run(case)
            return case, record, judge_report(case, record), None
        except (anthropic.APIError, RefusalError, TruncatedError) as exc:
            return case, None, [], str(exc)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(work, cases))

    direct = {}
    if HELDOUT_RESULTS.exists():
        for c in json.loads(HELDOUT_RESULTS.read_text(encoding="utf-8"))["cases"]:
            direct[c["case"]] = set(c["direct"])

    reports, precedent, recommendation, check = [], Counter(), Counter(), Counter()
    cited_direct = []
    for case, record, rows, error in outcomes:
        if error:
            print(f"  {case.id:9s} FAILED: {error[:90]}")
            continue
        for row in rows:
            precedent[row["precedent"]] += 1
            if row["recommendation"] not in ("none", "uncited"):
                recommendation[row["recommendation"]] += 1
            if row["check"] != "none":
                check[row["check"]] += 1
        cited = {c for row in rows for c in row["cited_ids"]}
        cited_docs = {c.split("#")[0] for c in cited}
        hit = bool(direct.get(case.id, set()) & cited_docs) if direct.get(case.id) else None
        if hit is not None:
            cited_direct.append((case.id, case.difficulty, hit))
        reports.append(
            {
                "case": case.id,
                "difficulty": case.difficulty,
                "model": record["model"],
                "cost_usd": record["cost_usd"],
                "tool_calls": len(record["steps"]),
                "unsupported_links": record["unsupported_links"],
                "cites_direct_precursor": hit,
                "risks": rows,
            }
        )
        marks = " ".join(
            f"{r['precedent'][:3]}/{r['recommendation'][:3]}/{r['check'][:3]}" for r in rows
        )
        print(f"  {case.id:9s} {len(rows)} risks  {marks}")

    n = sum(precedent.values())
    print(f"\n{len(reports)} reports, {n} risks, judged by {JUDGE_MODEL}")
    for name, counter in [
        ("precedent", precedent),
        ("recommendation", recommendation),
        ("check", check),
    ]:
        parts = ", ".join(f"{k} {v} ({share(counter, k):.0%})" for k, v in counter.most_common())
        print(f"  {name:15s} {parts}")
    if cited_direct:
        hits = sum(h for _, _, h in cited_direct)
        hard = [(h) for _, d, h in cited_direct if d == "hard"]
        print(
            f"  finished report cites a direct precursor: {hits} of {len(cited_direct)} "
            f"(hard cases {sum(hard)} of {len(hard)})"
        )
    costs = [r["cost_usd"] for r in reports]
    print(f"  agent cost ${sum(costs):.2f}, mean ${statistics.mean(costs):.3f} per report")

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "judge": JUDGE_MODEL,
                "risks": n,
                "precedent": dict(precedent),
                "recommendation": dict(recommendation),
                "check": dict(check),
                "cites_direct_precursor": [
                    {"case": c, "difficulty": d, "hit": h} for c, d, h in cited_direct
                ],
                "reports": reports,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"-> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
