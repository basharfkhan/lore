"""Read the human answers from the adjudication checklist and apply them to the dev labels.

Each row of evals/review/adjudication_checklist.md carries two yes/no answers (see
evals/criteria.yaml). Both yes is a 2, one is a 1, neither is a 0. Rows left blank or marked
"?" are skipped and reported.

    python -m lore.eval.adjudicate            # show what would change
    python -m lore.eval.adjudicate --apply    # rewrite evals/labels/*.yaml
"""

from __future__ import annotations

import argparse
import re

import yaml

from lore.eval.cases import EVAL_DIR, LABELS_DIR, load_cases

SHEET = EVAL_DIR / "review" / "adjudication_checklist.md"


def read_sheet(text: str, case_ids: dict[str, str]) -> tuple[dict, list]:
    """Return ({(case, doc_id): grade}, [(case, doc_id) left unanswered])."""
    answers, unanswered, case = {}, [], None
    for line in text.splitlines():
        if line.startswith("## "):
            case = case_ids.get(line[3:].strip())
        elif line.startswith("| [") and case:
            cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
            doc_id = re.search(r"\[(llis-\d+)", line).group(1)
            a, b = cells[1], cells[2]
            if a in ("y", "n") and b in ("y", "n"):
                answers[(case, doc_id)] = (a == "y") + (b == "y")
            else:
                unanswered.append((case, doc_id))
    return answers, unanswered


def apply(case_id: str, grades: dict[str, int], reviewer: str) -> None:
    path = LABELS_DIR / f"{case_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    relevant = {item["doc_id"]: item for item in data.get("relevant") or []}
    not_relevant = set(data.get("not_relevant") or [])
    for doc_id, grade in grades.items():
        not_relevant.discard(doc_id)
        if grade == 0:
            relevant.pop(doc_id, None)
            not_relevant.add(doc_id)
        else:
            item = relevant.setdefault(doc_id, {"doc_id": doc_id, "why": "Graded by checklist."})
            item["grade"] = grade
            item["adjudicated_by"] = reviewer
    data["relevant"] = list(relevant.values())
    data["not_relevant"] = sorted(not_relevant)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, width=100, allow_unicode=True), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewer", default="bashar")
    args = parser.parse_args()

    cases = {c.id: c for c in load_cases()}
    answers, unanswered = read_sheet(
        SHEET.read_text(encoding="utf-8"), {c.mishap: c.id for c in cases.values()}
    )
    changes: dict[str, dict[str, int]] = {}
    for (case_id, doc_id), grade in sorted(answers.items()):
        old = cases[case_id].labels.get(doc_id)
        flag = "" if old == grade else "  <- changes"
        print(f"  {case_id:13s} {doc_id:10s} draft {old} -> yours {grade}{flag}")
        changes.setdefault(case_id, {})[doc_id] = grade
    print(f"{len(answers)} answered, {len(unanswered)} still blank")
    if args.apply:
        for case_id, grades in changes.items():
            apply(case_id, grades, args.reviewer)
        print("labels updated")


if __name__ == "__main__":
    main()
