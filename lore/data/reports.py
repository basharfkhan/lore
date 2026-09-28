"""Download the mishap investigation reports listed in configs/reports.yaml.

Each PDF is checked for a PDF header (some NASA URLs answer a dead link with a 200 HTML page)
and recorded with its size and SHA-256 in data/raw/reports/manifest.json, so a later run can
tell whether NASA has changed a file underneath us.

    python -m lore.data.reports          # download anything missing
    python -m lore.data.reports --force  # re-download everything
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
import yaml

from lore.paths import CONFIG_DIR, RAW_DIR

CONFIG_PATH = CONFIG_DIR / "reports.yaml"
REPORTS_DIR = RAW_DIR / "reports"
MANIFEST_PATH = REPORTS_DIR / "manifest.json"
USER_AGENT = "lore-research/0.1 (portfolio project; public NASA documents)"


@dataclass(frozen=True)
class Report:
    id: str
    title: str
    mission: str
    mishap_date: date
    report_date: date
    url: str

    @property
    def path(self) -> Path:
        return REPORTS_DIR / f"{self.id}.pdf"


def load_reports(path: Path = CONFIG_PATH) -> list[Report]:
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))["reports"]
    reports = [Report(**entry) for entry in entries]
    ids = [r.id for r in reports]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate report ids in {path}")
    for r in reports:
        if r.report_date < r.mishap_date:
            raise ValueError(f"{r.id}: report_date is before mishap_date")
    return reports


def download(report: Report, session: requests.Session, timeout: float = 300) -> dict:
    tmp = report.path.with_suffix(".part")
    digest = hashlib.sha256()
    size = 0
    with session.get(report.url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    with tmp.open("rb") as f:
        if f.read(5) != b"%PDF-":
            tmp.unlink()
            raise ValueError(f"{report.id}: {report.url} did not return a PDF")
    tmp.replace(report.path)
    return {"url": report.url, "bytes": size, "sha256": digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    failures = []
    for report in load_reports():
        if report.path.exists() and report.id in manifest and not args.force:
            print(f"  have  {report.id}")
            continue
        try:
            manifest[report.id] = download(report, session)
            print(f"  got   {report.id}  {manifest[report.id]['bytes'] / 1e6:.1f} MB")
        except (requests.RequestException, ValueError) as exc:
            failures.append(report.id)
            print(f"  FAIL  {report.id}: {exc}")
        time.sleep(1)  # be polite to NASA's servers

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit(f"{len(failures)} report(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
