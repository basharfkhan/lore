"""Step 1 of a pre-mortem: turn a system description into failure hypotheses to search for.

Retrieving with the system description matches documents about the same *topic* (a Mars lander
pulls in Mars documents). Useful precursors share a *failure mechanism* and are usually about
other hardware, so each hypothesis carries a search query written in generic engineering terms,
with no mission or program names.
"""

from __future__ import annotations

from dataclasses import dataclass

from lore.llm import json_call

PROMPT_VERSION = 1
N_HYPOTHESES = 10

SYSTEM = """\
You are a senior spacecraft reliability engineer leading a pre-mortem. Assume the system \
described has failed, and work out the most plausible ways it could have failed, so the team \
can search NASA's lessons-learned archive for prior failures of the same kind.

Reason only from the description and general engineering knowledge. If the description \
reminds you of a real mission, do not use what you know about how that mission turned out; \
treat the system as new.

Cover different layers rather than variations on one theme: design and requirements, \
software and fault logic, verification and test gaps, integration and interfaces, operations, \
ground handling, and organisational or programmatic pressure.

For each hypothesis write a search query that would find lessons about the same failure \
mechanism on any program. Use generic engineering terms; never name a mission, spacecraft or \
program, since the most useful precursor is usually about different hardware."""

SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "failure_mode": {"type": "string"},
                    "mechanism": {"type": "string"},
                    "layer": {"type": "string"},
                    "search_query": {"type": "string"},
                },
                "required": ["failure_mode", "mechanism", "layer", "search_query"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}


@dataclass
class Hypothesis:
    failure_mode: str
    mechanism: str
    layer: str
    search_query: str


def generate(description: str, n: int = N_HYPOTHESES) -> list[Hypothesis]:
    user = (
        f"System under review:\n\n{description}\n\nGive the {n} most important failure hypotheses."
    )
    output = json_call(SYSTEM, user, SCHEMA)
    return [Hypothesis(**h) for h in output["hypotheses"]][:n]
