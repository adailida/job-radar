"""Deciding which postings describe the same job."""

from job_radar.matching.ats_links import AtsLinks
from job_radar.matching.normalizer import Normalizer
from job_radar.models import Posting


class JobKey:
    """Decides which postings describe the same job.

    Each posting has up to two identity keys. The ATS key is the employer's own
    id for the opening, read from the link ("greenhouse:acme:4012345"): the
    strongest. The fuzzy key is the company, the title and the countries, in
    canonical form ("acme|senior data engineer|US"), so "NYC" and "New York,
    NY" agree once both have codes; a place with no country code counts by its
    text. Stateless: holds only the normalizer and how links are read.
    """

    def __init__(self, normalizer: Normalizer, ats: AtsLinks) -> None:
        """Keep how names are put in canonical form, and how links become ATS keys."""
        self._normalize = normalizer
        self._ats = ats

    def keys(self, posting: Posting) -> tuple[str, ...]:
        """The posting's identity keys, strongest first: its ATS key if any, then its fuzzy key."""
        ats = self._ats.key(posting.url)
        return (ats, self.fuzzy(posting)) if ats else (self.fuzzy(posting),)

    def fuzzy(self, posting: Posting) -> str:
        """The company, title and countries in canonical form: "acme|senior data engineer|US"."""
        texts = [place.text for place in posting.locations]
        places = sorted(
            {place.country or self._normalize.place(place.text) for place in posting.locations}
        )
        company = self._normalize.company(posting.company)
        title = self._normalize.title(posting.title, texts)
        return f"{company}|{title}|{';'.join(places)}"
