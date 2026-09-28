"""Does the model recognise the mission behind each eval case?

The historical eval is only a test of reasoning if the model cannot simply remember how the
mission ended. This asks directly, per case, and records whether the named mission and the
recalled cause match the real ones. Results are reported next to the scores, not hidden.

    python -m lore.eval.contamination
"""

from __future__ import annotations

import json

from lore.eval.cases import EVAL_DIR, load_cases
from lore.llm import MODEL, json_call

SYSTEM = """\
You will see a short description of a spacecraft system or operation. Say whether you \
recognise it as a specific real mission or event, and if so, what you believe happened to it. \
Be candid: this is a test of whether the description is recognisable, not a quiz."""

SCHEMA = {
    "type": "object",
    "properties": {
        "recognised": {"type": "boolean"},
        "mission_guess": {"type": "string"},
        "confidence": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "what_happened": {"type": "string"},
    },
    "required": ["recognised", "mission_guess", "confidence", "what_happened"],
    "additionalProperties": False,
}


def main() -> None:
    results = []
    for case in load_cases():
        out = json_call(SYSTEM, case.query, SCHEMA, max_tokens=4000)
        results.append({"case": case.id, "actual": case.mishap, **out})
        print(
            f"{case.id:13s} recognised={out['recognised']!s:5s} ({out['confidence']:6s}) "
            f"guess: {out['mission_guess'][:60]}"
        )
    path = EVAL_DIR / "results" / "contamination.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"model": MODEL, "cases": results}, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
