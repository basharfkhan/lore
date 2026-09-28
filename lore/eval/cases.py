"""Load eval cases and their relevance labels."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from lore.paths import ROOT

EVAL_DIR = ROOT / "evals"
CASES_PATH = EVAL_DIR / "cases.yaml"
LABELS_DIR = EVAL_DIR / "labels"
POOL_DIR = EVAL_DIR / "pool"


@dataclass
class Case:
    id: str
    mishap: str
    report: str
    cutoff: date
    query: str
    hindsight_queries: list[str]
    failure_mechanism: str = ""
    # doc_id -> grade (0, 1, 2), empty until labelled
    labels: dict[str, int] = field(default_factory=dict)
    reviewed: bool = False

    @property
    def cutoff_iso(self) -> str:
        return self.cutoff.isoformat()

    @property
    def relevant(self) -> dict[str, int]:
        return {doc: g for doc, g in self.labels.items() if g > 0}


def load_labels(case_id: str) -> tuple[dict[str, int], bool]:
    path = LABELS_DIR / f"{case_id}.yaml"
    if not path.exists():
        return {}, False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    labels = {doc_id: 0 for doc_id in data.get("not_relevant") or []}
    for item in data.get("relevant") or []:
        if item["doc_id"] in labels:
            raise ValueError(f"{path.name}: {item['doc_id']} is both relevant and not relevant")
        labels[item["doc_id"]] = int(item["grade"])
    return labels, bool(data.get("reviewed_by"))


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    cases = []
    for entry in yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]:
        case = Case(**entry)
        case.labels, case.reviewed = load_labels(case.id)
        cases.append(case)
    return cases
