"""Turning HTML from job boards into plain text."""

import re
from html.parser import HTMLParser


class HtmlText:
    """Turns HTML into plain text that keeps its shape: paragraphs, line breaks and lists.

    Tags are dropped and entities decoded. Block elements become paragraphs,
    `<br>` a line break and each list item a "- " line, so a reader (or an
    LLM) still sees how the posting was laid out. Scripts and styles are left
    out. Stateless.
    """

    def text(self, html: str) -> str:
        """The plain text of an HTML fragment."""
        collector = _Collector()
        collector.feed(html)
        collector.close()
        return self._tidy("".join(collector.parts))

    def _tidy(self, raw: str) -> str:
        """Trim every line, start bullets, and allow at most one blank line in a row."""
        text = re.sub(_BULLET + r"\s*", "- ", raw)
        lines = [line.strip() for line in text.split("\n")]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        text = re.sub(r"\n\n+(?=- )", "\n", text)  # list items on consecutive lines
        return text.strip()


_BULLET = "\x00"  # marks where a list item starts, until the text is tidied

_BLOCKS = frozenset(
    "address article aside blockquote dd div dl dt figcaption figure footer form "
    "h1 h2 h3 h4 h5 h6 header hr main nav ol p pre section table tbody thead tr ul".split()
)
_HIDDEN = frozenset({"script", "style", "template", "noscript"})


class _Collector(HTMLParser):
    """Collects the text of one HTML fragment, with markers for its layout.

    Stateful: built for one fragment and dropped after it.
    """

    def __init__(self) -> None:
        """Start with no text, outside any hidden element."""
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Mark where a paragraph, line or list item starts."""
        if tag in _HIDDEN:
            self._hidden += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n" + _BULLET)
        elif tag in _BLOCKS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        """Mark where a paragraph or list item ends."""
        if tag in _HIDDEN:
            self._hidden = max(0, self._hidden - 1)
        elif tag == "li":
            self.parts.append("\n")
        elif tag in _BLOCKS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        """Keep visible text, with runs of whitespace as one space, as a browser shows it."""
        if not self._hidden:
            self.parts.append(re.sub(r"\s+", " ", data))
