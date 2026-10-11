"""The pre-mortem agent: Claude with archive tools, choosing what to look up and citing it.

The loop is written out by hand so each step is visible to the caller (the web UI shows the
searches as they happen) and so the run can be audited afterwards: every link in the final
answer is checked against the documents the tools returned during that run.

    python -m lore.agent.premortem "We are lifting a satellite with a borrowed fixture..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from lore.agent.tools import TOOLS, run_tool
from lore.llm import FALLBACK_BETA, client
from lore.paths import DATA_DIR

# Sonnet followed the report format and stayed within the sources at 40% of the Opus cost in
# side-by-side runs; Haiku was cheapest but added advice the sources do not contain.
DEFAULT_MODEL = os.environ.get("LORE_AGENT_MODEL", "claude-sonnet-5")
MAX_TURNS = 10
MAX_TOKENS = 8000
RUNS_DIR = DATA_DIR / "interim" / "runs"

# Dollars per million tokens (input, output). Cache reads bill at 0.1x input, writes at 1.25x.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

SYSTEM = """\
You are LORE, a pre-mortem assistant for spacecraft and space-mission engineers. The user \
describes a system, an operation or a design decision. Your job is to find what has gone wrong \
before in situations like it, using NASA's lessons-learned archive and mishap investigation \
reports, and to tell them what the investigators recommended.

How to work:
1. Think of the distinct ways the described system could fail: design, software and fault \
logic, test and verification gaps, interfaces between teams, operations, ground handling, and \
schedule or cost pressure. Pick the ones that matter most for this system.
2. Search the archive once per failure mode, in generic engineering terms. Do not search for \
the user's mission or hardware by name; the best precedent is usually about different hardware \
that failed the same way.
3. Read the promising results in full before relying on them.
4. Write the pre-mortem.

The report:
- Start with one or two sentences on the overall picture.
- Then three to five risks, most serious first, each under a short heading. For each, in about \
80 words: what could go wrong for this system; the precedent (what happened, to what, and \
when); and what the investigators recommended. Close each with one "Check:" line that applies \
that recommendation to the user's system.
- The whole report should fit on one screen: 350 to 500 words. One strong precedent per risk \
is better than several weak ones.
- Recommendations and checks must come from the documents. Do not add numeric thresholds, \
margins or procedures of your own; if you add a general engineering point the documents do not \
make, label it as your own suggestion.
- Cite every precedent as a markdown link using the exact title and url the tools returned, \
for example [LLIS 267: TOPEX/POSEIDON Near-Drop Incident](https://llis.nasa.gov/lesson/267).
- Only describe precedents you retrieved in this conversation, and only say what the documents \
say. If the archive has nothing relevant on a risk you think matters, say so plainly rather \
than filling the gap from memory.
- End with one line noting that this is a research aid drawn from historical records, not a \
safety review.

For follow-up questions, answer directly, searching again when needed. Write plainly for a \
working engineer.

You only do pre-mortems and questions about this archive. If asked for anything else, say so \
in one sentence without calling tools."""


@dataclass
class Run:
    answer: str = ""
    steps: list[dict] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)  # url -> title, from tool results
    unsupported_links: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    model: str = ""
    messages: list[dict] = field(default_factory=list)


def _request(model: str, messages: list[dict], allow_tools: bool):
    kwargs = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "tools": TOOLS,
        "messages": messages,
        # Caches the growing prefix, so each loop turn re-reads earlier turns at a tenth the price.
        "cache_control": {"type": "ephemeral"},
    }
    if not allow_tools:
        kwargs["tool_choice"] = {"type": "none"}
    if model.startswith("claude-opus-5"):
        # Server-side fallback if a safety classifier declines the request.
        return client().beta.messages.create(**kwargs, betas=[FALLBACK_BETA], fallbacks="default")
    return client().messages.create(**kwargs)


def _collect_sources(result, sources: dict[str, str]) -> None:
    for item in result if isinstance(result, list) else [result]:
        if isinstance(item, dict) and item.get("url"):
            sources[item["url"]] = item.get("title", "")


def check_links(answer: str, sources: dict[str, str]) -> list[str]:
    """Links in the answer that no tool returned during this run."""
    links = set(re.findall(r"\]\((https?://[^)\s]+)\)", answer))
    known = set(sources) | {u.split("#")[0] for u in sources}
    return sorted(u for u in links if u not in known and u.split("#")[0] not in known)


def _cost(model: str, usage: dict[str, int]) -> float:
    price_in, price_out = PRICES.get(model, PRICES["claude-opus-5"])
    return (
        usage.get("input_tokens", 0) * price_in
        + usage.get("cache_read_input_tokens", 0) * price_in * 0.1
        + usage.get("cache_creation_input_tokens", 0) * price_in * 1.25
        + usage.get("output_tokens", 0) * price_out
    ) / 1e6


def run(
    question: str,
    history: list[dict] | None = None,
    model: str = DEFAULT_MODEL,
    on_step: Callable[[dict], None] | None = None,
    sources: dict[str, str] | None = None,
) -> Run:
    """Answer one user turn.

    For a follow-up, pass the previous Run's ``messages`` as ``history`` and its ``sources``,
    so a link to a document retrieved earlier in the conversation still counts as supported.
    """
    out = Run(
        model=model,
        messages=[*(history or []), {"role": "user", "content": question}],
        sources=dict(sources or {}),
    )
    totals: dict[str, int] = {}
    for turn in range(MAX_TURNS + 1):
        response = _request(model, out.messages, allow_tools=turn < MAX_TURNS)
        for key, value in response.usage.to_dict().items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
        out.messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "refusal":
            out.answer = "The model declined to answer this request."
            break
        calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            out.answer = "\n".join(b.text for b in response.content if b.type == "text").strip()
            break
        results = []
        for call in calls:
            result = run_tool(call.name, call.input)
            _collect_sources(result, out.sources)
            step = {"tool": call.name, "input": call.input}
            out.steps.append(step)
            if on_step:
                on_step(step)
            results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": json.dumps(result)}
            )
        # All results go back in one message, as the API expects for parallel tool calls.
        out.messages.append({"role": "user", "content": results})

    out.unsupported_links = check_links(out.answer, out.sources)
    out.usage = totals
    out.cost_usd = round(_cost(model, totals), 4)
    return out


def save(result: Run, question: str) -> Path:
    """Write a run to disk before anything else can fail: the answer was paid for."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    path = RUNS_DIR / f"{stamp}-{result.model}.json"
    record = {
        "question": question,
        "model": result.model,
        "answer": result.answer,
        "steps": result.steps,
        "sources": result.sources,
        "unsupported_links": result.unsupported_links,
        "usage": result.usage,
        "cost_usd": result.cost_usd,
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    # Windows consoles default to cp1252 and fail on characters the model may use.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    result = run(
        args.question,
        model=args.model,
        on_step=lambda s: print(f"  [{s['tool']}] {s['input']}", flush=True),
    )
    path = save(result, args.question)
    print(f"\n{result.answer}\n")
    print(
        f"-- {result.model}: {len(result.steps)} tool calls, {len(result.sources)} sources seen, "
        f"${result.cost_usd:.3f}, unsupported links: {result.unsupported_links or 'none'}\n"
        f"-- saved to {path}"
    )


if __name__ == "__main__":
    main()
