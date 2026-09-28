"""Turn the HTML fragments LLIS stores into plain text that keeps paragraph breaks."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

# Tags that end a line of prose. Everything else (u, b, span, a...) is inline.
_BLOCK_TAGS = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"}

# LLIS uses these as "nothing here" markers in otherwise free-text fields.
_EMPTY_MARKERS = {"", "none", "n/a", "na", "tbd", "not applicable", "not specified"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(fragment: str | None) -> str:
    """Plain text with one blank line between paragraphs and no runs of spaces."""
    if not fragment:
        return ""
    parser = _TextExtractor()
    parser.feed(fragment)
    parser.close()
    text = unescape("".join(parser.parts)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return "" if text.lower().rstrip(".") in _EMPTY_MARKERS else text
