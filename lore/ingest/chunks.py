"""Split lessons and report pages into retrieval chunks with citation and date metadata.

Every chunk carries two things the rest of LORE depends on:

* ``available_from``: the first day anyone could have read it (a lesson's date, a report's
  release date). The historical eval filters on this, so a pre-mortem for Mars Climate
  Orbiter can never retrieve the board report written after it was lost.
* A citation: the lesson URL, or the report URL with ``#page=N`` for the first page.

LLIS lessons are short (median ~1,600 characters), so most become a single chunk. Reports are
streamed page by page: running headers and page numbers are stripped, hard-wrapped lines are
rejoined into paragraphs, and paragraphs are packed into chunks that break at section headings.

    python -m lore.ingest.chunks
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field

from lore.data.reports import Report, load_reports
from lore.paths import PROCESSED_DIR

LLIS_PATH = PROCESSED_DIR / "llis.jsonl"
PAGES_PATH = PROCESSED_DIR / "pages.jsonl"
OUT_PATH = PROCESSED_DIR / "chunks.jsonl"

# Characters, not tokens: roughly 4 characters per token for this English prose, so a target of
# 2,400 is ~600 tokens. Small enough that a chunk is about one thing, large enough to hold a
# finding together with its explanation.
TARGET_CHARS = 2400
MAX_CHARS = 3200
# A heading only starts a new chunk once the current one has this much in it; otherwise a run
# of short numbered sections would produce a string of fragments.
MIN_CHARS_BEFORE_HEADING_BREAK = 800
# Chunks shorter than this carry no retrievable content (a lone caption, a signature block).
MIN_CHUNK_CHARS = 200

# A line counts as a running header/footer when it sits in the first or last few lines of a
# page and, with digits masked, recurs on enough of the report's pages. Lines carrying a number
# (almost always a page number) need fewer repeats: Genesis alternates "Page N Genesis Mishap
# Report" and "Genesis Mishap Report Page N" between facing pages, so each variant is on only
# ~17% of them.
BOILERPLATE_EDGE_LINES = 3
BOILERPLATE_MIN_SHARE = 0.2
BOILERPLATE_MIN_SHARE_NUMBERED = 0.08
# Share of tokens that look like words. Prose scores ~0.8; OCR'd org charts and number tables
# fall well under this and are dropped rather than indexed as noise.
MIN_WORDLIKE_SHARE = 0.5

_PAGE_NUMBER = re.compile(r"^(page\s*)?[\divxlc]+(\s*of\s*\d+)?\.?$|^-\s*\d+\s*-$", re.IGNORECASE)
_PAGE_REF = re.compile(
    r"\bpage\s+(?:[a-z]-?)?(?:\d+|[ivxlc]+\b)?|\b\d+\s+of\s+\d+\b", re.IGNORECASE
)
_TOC_LINE = re.compile(r"(\.\s*){4,}\s*\d+\s*$")
_NUMBERED_HEADING = re.compile(r"^(\d+(\.\d+)*\.?|[A-Z]\.|[IVX]+\.|Appendix [A-Z0-9]+[.:]?)\s+[A-Z]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


@dataclass
class Chunk:
    id: str
    source: str  # "llis" | "report"
    doc_id: str
    doc_title: str
    section: str | None
    text: str
    available_from: str
    url: str
    pages: list[int] | None = None
    mishap_date: str | None = None  # reports only: the failure the document is about
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.char_count = len(self.text)

    @property
    def context(self) -> str:
        """Header prepended when embedding, so a chunk out of context still says what it is from."""
        return f"{self.doc_title} - {self.section}" if self.section else self.doc_title


# --- text cleanup --------------------------------------------------------------------------


def normalise_chars(text: str) -> str:
    text = text.replace("\xa0", " ").replace("", "•")
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", text)  # stray control characters from PDF fonts
    # Soft hyphens mark a break the typesetter chose, so the word is always rejoined; a real
    # hyphen at a line end is rejoined only between lowercase letters (in-\nspection), which
    # keeps "Mars-\nObserver" style compounds intact at the cost of rare mistakes.
    text = re.sub(r"\xad\s*\n\s*", "", text).replace("\xad", "")
    return re.sub(r"(?<=[a-z])-\n\s*(?=[a-z])", "", text)


def is_heading(line: str) -> bool:
    line = line.strip()
    if not 3 <= len(line) <= 90 or line.endswith((".", ",", ";")):
        return False
    words = line.split()
    if len(words) > 12:
        return False
    if _NUMBERED_HEADING.match(line):
        return True
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def boilerplate_lines(pages: list[str]) -> set[str]:
    """Masked lines that recur at the top or bottom of many pages: running headers, footers."""
    if len(pages) < 5:
        return set()
    counts: Counter[str] = Counter()
    numbered_keys: set[str] = set()
    for text in pages:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        edges = {_mask(ln) for ln in lines[:BOILERPLATE_EDGE_LINES] + lines[-BOILERPLATE_EDGE_LINES:]}
        # Plain lines only count at the page edges, so a recurring heading such as FINDINGS
        # survives. Numbered lines count anywhere: text-layer order can put a footer mid-page.
        numbered = {_mask(ln) for ln in lines if _PAGE_REF.search(ln)}
        numbered_keys |= numbered
        # A key needs real words: "R3.3-1" style finding numbers mask down to punctuation
        # and must never be mistaken for a running header.
        counts.update(k for k in edges | numbered if sum(c.isalpha() for c in k) >= 4)
    plain_min = max(3, BOILERPLATE_MIN_SHARE * len(pages))
    numbered_min = max(3, BOILERPLATE_MIN_SHARE_NUMBERED * len(pages))
    return {
        key for key, n in counts.items() if n >= (numbered_min if key in numbered_keys else plain_min)
    }


def wordlike_share(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    words = sum(bool(re.fullmatch(r"[(\"']?[A-Za-z][A-Za-z'\-]*[.,;:)\"']*", t)) for t in tokens)
    return words / len(tokens)


def _mask(line: str) -> str:
    """Reduce a line to the part that stays the same across pages.

    Page references ("Page 32", "Page E-4", "Page I", "12 of 18") and bare numbers are removed,
    so "Page 32 Genesis Mishap Report" and "Genesis Mishap Report Page E-4" share one key.
    """
    line = _PAGE_REF.sub(" ", line.lower())
    line = re.sub(r"\d+", " ", line)
    return re.sub(r"\s+", " ", line).strip(" .-")


def paragraphs(text: str, drop: set[str]) -> Iterator[tuple[str, bool]]:
    """Yield (paragraph, is_heading) from one page, rejoining hard-wrapped lines."""
    buffer: list[str] = []

    def flush() -> Iterator[tuple[str, bool]]:
        if buffer:
            yield " ".join(buffer), False
            buffer.clear()

    for raw in normalise_chars(text).splitlines():
        line = raw.strip()
        if not line:
            yield from flush()
            continue
        if _mask(line) in drop or _PAGE_NUMBER.match(line) or _TOC_LINE.search(line):
            continue
        if is_heading(line):
            yield from flush()
            yield line, True
            continue
        buffer.append(line)
        # A line that ends a sentence well short of the margin usually ends a paragraph.
        if line.endswith((".", ":", "?", "!")) and len(line) < 55:
            yield from flush()
    yield from flush()


def split_long(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Break an oversized paragraph at sentence boundaries, hard-cutting only as a last resort."""
    if len(text) <= limit:
        return [text]
    pieces, current = [], ""
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > limit:  # a table or run-on OCR with no sentence breaks
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:limit])
            sentence = sentence[limit:]
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


# --- packing -------------------------------------------------------------------------------


@dataclass
class _Piece:
    text: str
    page: int | None
    heading: bool = False


def pack(pieces: Iterable[_Piece]) -> Iterator[tuple[str, str | None, list[int]]]:
    """Greedily pack paragraphs into (text, section, pages) chunks, breaking at headings."""
    section: str | None = None
    parts: list[str] = []
    pages: list[int] = []
    chunk_section: str | None = None
    size = 0

    def emit() -> Iterator[tuple[str, str | None, list[int]]]:
        nonlocal parts, pages, size
        if parts:
            yield "\n\n".join(parts), chunk_section, sorted(set(pages))
        parts, pages, size = [], [], 0

    for piece in pieces:
        if piece.heading:
            if size >= MIN_CHARS_BEFORE_HEADING_BREAK:
                yield from emit()
            section = piece.text
            if not parts:
                chunk_section = section
            # The heading stays in the text too: it is often the most descriptive phrase.
        for text in split_long(piece.text):
            if parts and size + len(text) > TARGET_CHARS:
                yield from emit()
            if not parts:
                chunk_section = section
            parts.append(text)
            if piece.page is not None:
                pages.append(piece.page)
            size += len(text) + 2
    yield from emit()


# --- sources -------------------------------------------------------------------------------


def llis_chunks(lessons: Iterable[dict]) -> Iterator[Chunk]:
    for lesson in lessons:
        labelled = [
            ("Abstract", lesson["abstract"]),
            ("Driving event", lesson["driving_event"]),
            ("Lesson", lesson["lesson"]),
            ("Recommendation", lesson["recommendation"]),
        ]
        pieces: list[_Piece] = []
        for label, body in labelled:
            if not body:
                continue
            pieces.append(_Piece(label, None, heading=True))
            pieces.extend(_Piece(p, None) for p in body.split("\n\n") if p.strip())
        title = f"LLIS {lesson['lesson_number']}: {lesson['title']}"
        # A lesson is one argument (what happened, what it taught, what to do), so it stays
        # whole whenever it fits; only the long ones go through the packer.
        whole = "\n\n".join(p.text for p in pieces)
        packed = [(whole, None, [])] if len(whole) <= MAX_CHARS else list(pack(pieces))
        for i, (text, section, _) in enumerate(packed):
            yield Chunk(
                id=f"{lesson['id']}#{i}",
                source="llis",
                doc_id=lesson["id"],
                doc_title=title,
                section=section if len(packed) > 1 else None,
                text=text,
                available_from=lesson["date"],
                url=lesson["url"],
            )


def report_chunks(report: Report, pages: list[dict]) -> Iterator[Chunk]:
    readable = [p for p in pages if p["method"] in ("text_layer", "ocr") and p["text"]]
    drop = boilerplate_lines([p["text"] for p in readable])
    pieces = (
        _Piece(text, page["page"], heading)
        for page in readable
        for text, heading in paragraphs(page["text"], drop)
    )
    for i, (text, section, page_numbers) in enumerate(pack(pieces)):
        if len(text) < MIN_CHUNK_CHARS or wordlike_share(text) < MIN_WORDLIKE_SHARE:
            continue
        yield Chunk(
            id=f"report-{report.id}#{i}",
            source="report",
            doc_id=f"report-{report.id}",
            doc_title=report.title,
            section=section,
            text=text,
            available_from=report.report_date.isoformat(),
            url=f"{report.url}#page={page_numbers[0]}",
            pages=page_numbers,
            mishap_date=report.mishap_date.isoformat(),
        )


def _read_jsonl(path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main() -> None:
    lessons = _read_jsonl(LLIS_PATH)
    pages_by_report: dict[str, list[dict]] = {}
    for page in _read_jsonl(PAGES_PATH):
        pages_by_report.setdefault(page["report_id"], []).append(page)

    chunks = list(llis_chunks(lessons))
    n_llis = len(chunks)
    for report in load_reports():
        chunks.extend(report_chunks(report, pages_by_report.get(report.id, [])))

    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        for chunk in chunks:
            record = asdict(chunk) | {"context": chunk.context}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    sizes = [c.char_count for c in chunks]
    print(
        f"{len(chunks)} chunks ({n_llis} from {len(lessons)} lessons, "
        f"{len(chunks) - n_llis} from reports) -> {OUT_PATH}\n"
        f"chars: median {statistics.median(sizes):.0f}, max {max(sizes)}"
    )


if __name__ == "__main__":
    main()
