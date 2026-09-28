"""Extract per-page text from the mishap reports, running OCR only where it is needed.

Three kinds of page turn up in the corpus, and each gets a different treatment:

* Born-digital pages (Genesis, MCO, DART...) have a real text layer. It is used as is.
* Old scans whose embedded OCR layer is one word per line (Apollo 1, Apollo 13, Mars Polar
  Lander, SOHO). The words are there but lines, columns and paragraphs are gone, which would
  wreck chunking, so the whole document is OCR'd again with Tesseract's layout analysis.
* Image-only pages inside otherwise good documents: signed endorsement letters, photo
  captions, scanned appendices. These get OCR'd individually. The NOAA N-Prime endorsement,
  where NASA's safety chief disputes some of the board's findings, is one of them.

    python -m lore.ingest.pages               # all reports, OCR results cached per page
    python -m lore.ingest.pages --only soho   # one report
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from lore.data.reports import load_reports
from lore.paths import DATA_DIR, PROCESSED_DIR

OUT_PATH = PROCESSED_DIR / "pages.jsonl"
OCR_CACHE = DATA_DIR / "interim" / "ocr"

OCR_DPI = 300
# A page with less text than this is treated as having no text layer.
MIN_LAYER_CHARS = 50
# A document is "one word per line" when its median line holds fewer words than this.
# Real prose sits between 5 and 11 here; the broken scans sit at 1.0 to 1.9.
MIN_WORDS_PER_LINE = 3.0
# Below this mean word confidence, try detecting the page's orientation and OCR it again.
RETRY_ROTATION_BELOW = 70.0
# Below this, even after the retry, the "text" is Tesseract reading a photo or a smudge.
# Such pages stay in pages.jsonl as "illegible" so they are counted but never indexed.
MIN_OCR_CONFIDENCE = 50.0
# Bump when OCR settings change so cached pages are redone.
OCR_CACHE_VERSION = 2

_WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


@dataclass
class Page:
    report_id: str
    page: int  # 1-based, matches a PDF viewer and #page=N links
    method: str  # "text_layer" | "ocr" | "illegible" | "blank"
    text: str
    ocr_confidence: float | None = None
    rotation: int = 0


def configure_tesseract() -> None:
    cmd = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
    if not cmd and _WINDOWS_TESSERACT.exists():
        cmd = str(_WINDOWS_TESSERACT)
    if not cmd:
        raise RuntimeError("Tesseract not found; install it or set TESSERACT_CMD")
    pytesseract.pytesseract.tesseract_cmd = cmd


def median_words_per_line(doc: pymupdf.Document) -> float:
    ratios = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        lines = sum(len(b["lines"]) for b in blocks if b["type"] == 0)
        if lines:
            ratios.append(len(page.get_text("words")) / lines)
    return statistics.median(ratios) if ratios else 0.0


def plan(doc: pymupdf.Document) -> list[str]:
    """Decide per page: 'text_layer', 'ocr' or 'blank'."""
    rescan_all = median_words_per_line(doc) < MIN_WORDS_PER_LINE
    decisions = []
    for page in doc:
        has_text = len(page.get_text().strip()) >= MIN_LAYER_CHARS
        if rescan_all or (not has_text and page.get_images()):
            decisions.append("ocr")
        elif has_text:
            decisions.append("text_layer")
        else:
            decisions.append("blank")
    return decisions


def _ocr_lines(data: dict) -> tuple[str, float | None]:
    """Rebuild text from image_to_data: lines joined by spaces, paragraphs by a blank line."""
    paragraphs: dict[tuple, dict[tuple, list[str]]] = {}
    confidences = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        confidences.append(conf)
        para = (data["block_num"][i], data["par_num"][i])
        line = para + (data["line_num"][i],)
        paragraphs.setdefault(para, {}).setdefault(line, []).append(word)
    text = "\n\n".join(
        "\n".join(" ".join(words) for words in lines.values()) for lines in paragraphs.values()
    )
    return text, (round(statistics.mean(confidences), 1) if confidences else None)


def _ocr(image: Image.Image) -> tuple[str, float | None]:
    return _ocr_lines(pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT))


def _detected_rotation(image: Image.Image) -> int:
    """Degrees clockwise Tesseract says the page must turn to read upright, or 0 if unsure."""
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError:  # too little text to judge orientation
        return 0
    return int(osd["rotate"])


def ocr_page(pdf_path: str, index: int, cache_path: str) -> tuple[str, float | None, int]:
    cache = Path(cache_path)
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("version") == OCR_CACHE_VERSION:
            return cached["text"], cached["confidence"], cached["rotation"]
    configure_tesseract()
    with pymupdf.open(pdf_path) as doc:
        pix = doc[index].get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    text, confidence = _ocr(image)
    rotation = 0
    # Landscape tables in the old scans were bound sideways and "intentionally blank" stamps
    # were printed upside down. Both OCR into mirror-text gibberish at low confidence, so
    # only those pages pay for orientation detection.
    if confidence is None or confidence < RETRY_ROTATION_BELOW:
        angle = _detected_rotation(image)
        # OSD's sign convention for 90/270 is easy to get backwards, so try both directions
        # (they coincide for 180) and keep whichever reads best.
        for turn in dict.fromkeys([-angle, angle]) if angle else ():
            retry_text, retry_conf = _ocr(image.rotate(turn, expand=True))
            if (retry_conf or 0) > (confidence or 0):
                text, confidence, rotation = retry_text, retry_conf, -turn % 360
    cache.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "version": OCR_CACHE_VERSION,
        "text": text,
        "confidence": confidence,
        "rotation": rotation,
    }
    cache.write_text(json.dumps(record), encoding="utf-8")
    return text, confidence, rotation


def extract_report(report_id: str, pdf_path: Path, pool: ProcessPoolExecutor) -> list[Page]:
    with pymupdf.open(pdf_path) as doc:
        decisions = plan(doc)
        layer_text = [
            p.get_text() if d == "text_layer" else "" for p, d in zip(doc, decisions, strict=True)
        ]

    futures = {
        i: pool.submit(ocr_page, str(pdf_path), i, str(OCR_CACHE / report_id / f"{i + 1:04d}.json"))
        for i, d in enumerate(decisions)
        if d == "ocr"
    }
    pages = []
    for i, decision in enumerate(decisions):
        if decision == "ocr":
            text, conf, rotation = futures[i].result()
            if not text.strip():
                method = "blank"
            elif conf is None or conf < MIN_OCR_CONFIDENCE:
                method, text = "illegible", ""
            else:
                method = "ocr"
            pages.append(Page(report_id, i + 1, method, text.strip(), conf, rotation))
        else:
            pages.append(Page(report_id, i + 1, decision, layer_text[i].strip()))
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="report ids to process")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()

    configure_tesseract()
    reports = [r for r in load_reports() if not args.only or r.id in args.only]
    existing = {}
    if args.only and OUT_PATH.exists():
        for line in OUT_PATH.read_text(encoding="utf-8").splitlines():
            page = json.loads(line)
            existing.setdefault(page["report_id"], []).append(page)

    results = dict(existing)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for report in reports:
            if not report.path.exists():
                raise SystemExit(f"{report.path} missing; run python -m lore.data.reports")
            start = time.perf_counter()
            pages = extract_report(report.id, report.path, pool)
            results[report.id] = [asdict(p) for p in pages]
            methods = ("text_layer", "ocr", "illegible", "blank")
            counts = {m: n for m in methods if (n := sum(p.method == m for p in pages))}
            if rotated := sum(p.rotation != 0 for p in pages):
                counts["rotated"] = rotated
            confs = [p.ocr_confidence for p in pages if p.method == "ocr"]
            conf = f", mean OCR confidence {statistics.mean(confs):.0f}" if confs else ""
            print(f"  {report.id:22s} {counts}{conf}  {time.perf_counter() - start:.0f}s")

    order = [r.id for r in load_reports()]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        for report_id in sorted(results, key=order.index):
            for page in results[report_id]:
                f.write(json.dumps(page, ensure_ascii=False) + "\n")
    print(f"{sum(len(v) for v in results.values())} pages -> {OUT_PATH}")


if __name__ == "__main__":
    main()
