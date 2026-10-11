"""Ship the searchable corpus with the repo so the service starts without the data pipeline.

data/ is not tracked (it holds 250 MB of PDFs and intermediate files), but the two files the
agent's tools read are only 6 MB compressed. ``export`` writes them to corpus/, which is
tracked; ``ensure`` unpacks them on a fresh checkout such as the deployed container.

    python -m lore.serve.corpus     # refresh corpus/ after rebuilding chunks
"""

from __future__ import annotations

import gzip
import shutil

from lore.paths import PROCESSED_DIR, ROOT

CORPUS_DIR = ROOT / "corpus"
FILES = ["chunks.jsonl", "llis.jsonl"]


def export() -> None:
    CORPUS_DIR.mkdir(exist_ok=True)
    for name in FILES:
        target = CORPUS_DIR / f"{name}.gz"
        # mtime=0 keeps the archive byte-identical when the content has not changed.
        with (
            (PROCESSED_DIR / name).open("rb") as src,
            target.open("wb") as raw,
            gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as dst,
        ):
            shutil.copyfileobj(src, dst)
        print(f"{name} -> {target} ({target.stat().st_size / 1e6:.1f} MB)")


def ensure() -> None:
    """Unpack corpus/*.gz into data/processed if the pipeline outputs are not there."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = PROCESSED_DIR / name
        if not target.exists():
            with gzip.open(CORPUS_DIR / f"{name}.gz", "rb") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


if __name__ == "__main__":
    export()
