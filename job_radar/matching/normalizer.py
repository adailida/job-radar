"""Text in a canonical form, so names written differently compare equal."""

import re
import unicodedata
from collections.abc import Iterable


class Normalizer:
    """Turns company names, job titles and places into a canonical form for comparing.

    Lowercase, no accents or punctuation, single spaces. Companies also lose
    legal suffixes; titles lose bracketed asides about place or work mode, and
    have common abbreviations spelled out. Stateless.
    """

    LEGAL_SUFFIXES = frozenset(
        {"inc", "incorporated", "llc", "ltd", "limited", "gmbh", "corp", "corporation", "plc", "co"}
    )
    ABBREVIATIONS = {
        "sr": "senior",
        "jr": "junior",
        "eng": "engineer",
        "engr": "engineer",
        "mgr": "manager",
        "dev": "developer",
        "swe": "software engineer",
    }
    BRACKETED = re.compile(r"\([^)]*\)|\[[^\]]*\]")
    PLACE_WORDS = frozenset(
        {"remote", "hybrid", "onsite", "on", "site", "in", "office", "anywhere", "global"}
        | {"worldwide", "us", "usa", "uk", "eu", "emea", "latam", "apac", "only", "or", "and"}
    )

    def company(self, name: str) -> str:
        """A company name without legal suffixes: "Acme, Inc." becomes "acme"."""
        words = self._words(name)
        while len(words) > 1 and words[-1] in self.LEGAL_SUFFIXES:
            words.pop()
        return " ".join(words)

    def title(self, title: str, places: Iterable[str] = ()) -> str:
        """A job title with abbreviations spelled out and asides about place removed.

        An aside in brackets goes only when all its words are about place or
        work mode, counting the words of the posting's own places: "Sr. Data
        Eng (Remote, US)" becomes "senior data engineer", while "Specialist
        (Media and Communication)" keeps its aside, which tells roles apart.
        """
        known = self.PLACE_WORDS | {word for place in places for word in self._words(place)}

        def drop_place(aside: re.Match[str]) -> str:
            """Remove an aside made only of place words; keep any other."""
            return " " if set(self._words(aside.group())) <= known else aside.group()

        words = self._words(self.BRACKETED.sub(drop_place, title))
        return " ".join(self.ABBREVIATIONS.get(word, word) for word in words)

    def place(self, place: str) -> str:
        """A place name in canonical form: "São Paulo, Brazil" becomes "sao paulo brazil"."""
        return " ".join(self._words(place))

    def _words(self, text: str) -> list[str]:
        """The text's words, lowercase, without accents or punctuation."""
        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        return re.findall(r"[a-z0-9]+", plain.lower())
