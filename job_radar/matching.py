"""Checking one job against one search."""

from decimal import Decimal

from job_radar.model import (
    Classification,
    Domains,
    IfMissing,
    Job,
    MinSalary,
    Period,
    Places,
    Posting,
    Search,
    Seniorities,
    Seniority,
    WorkMode,
    WorkModes,
)
from job_radar.normalize import Normalizer


class JobMatcher:
    """Says whether a job meets a search, and if not, which criterion it fails first.

    Checks the job's primary posting, and its labels once it has them:
    seniority and domain are skipped until the job is classified. A criterion
    the posting says nothing about follows the criterion's `if_missing`. Titles
    compare as whole words in canonical form, so "intern" doesn't match
    "International". Stateless: holds only the normalizer.
    """

    YEARLY = {Period.YEAR: Decimal(1), Period.MONTH: Decimal(12), Period.HOUR: Decimal(2080)}

    def __init__(self, normalizer: Normalizer) -> None:
        """Keep how titles are put in canonical form."""
        self._normalize = normalizer

    def miss(self, job: Job, search: Search) -> str | None:
        """The first criterion the job fails, such as "roles" or "location"; None if it matches."""
        posting = job.postings[0]
        if search.roles and not self._title_has(posting, search.roles):
            return "roles"
        if search.exclude_titles and self._title_has(posting, search.exclude_titles):
            return "excluded title"
        if search.work_mode and not self._work_mode(posting, search.work_mode):
            return "work mode"
        if search.locations and not self._places(posting, search.locations):
            return "location"
        if search.min_salary and not self._salary(posting, search.min_salary):
            return "salary"
        labels = job.classification
        if labels is not None and search.seniority and not self._level(labels, search.seniority):
            return "seniority"
        if labels is not None and search.domains and not self._domain(labels, search.domains):
            return "domain"
        return None

    def _level(self, labels: Classification, wanted: Seniorities) -> bool:
        """Whether the job's level is one wanted; unknown counts as missing."""
        known = None if labels.seniority is Seniority.UNKNOWN else labels.seniority in wanted.values
        return self._decide(known, wanted.if_missing)

    def _domain(self, labels: Classification, wanted: Domains) -> bool:
        """Whether the job's domain is one wanted; none counts as missing."""
        known = None if labels.domain is None else labels.domain in wanted.values
        return self._decide(known, wanted.if_missing)

    def _title_has(self, posting: Posting, words: tuple[str, ...]) -> bool:
        """Whether the title contains any of these, as whole words, any case."""
        title = f" {self._normalize.title(posting.title)} "
        return any(f" {self._normalize.title(word)} " in title for word in words)

    @staticmethod
    def _decide(found: bool | None, if_missing: IfMissing) -> bool:
        """A check's result, with "the posting doesn't say" (None) settled by `if_missing`."""
        return found if found is not None else if_missing is IfMissing.KEEP

    def _work_mode(self, posting: Posting, wanted: WorkModes) -> bool:
        """Whether the posting's work mode is one wanted; unknown counts as missing."""
        mode = posting.work_mode
        known = None if mode is WorkMode.UNKNOWN else mode in wanted.values
        return self._decide(known, wanted.if_missing)

    def _places(self, posting: Posting, wanted: Places) -> bool:
        """Whether a place of the posting is in a wanted country or region.

        Missing when the posting names no country at all ("Remote"), or names a
        wanted country without the region a value asks for. A posting that names
        only other countries ("India; Remote") doesn't match.
        """
        missing = not any(location.country for location in posting.locations)
        for location in posting.locations:
            for code in wanted.values:
                country, _, region = code.partition("-")
                if location.country != country:
                    continue
                if not region or location.region == code:
                    return True
                missing = missing or location.region is None
        return self._decide(None if missing else False, wanted.if_missing)

    def _salary(self, posting: Posting, wanted: MinSalary) -> bool:
        """Whether the top of the posting's pay reaches the minimum, both made yearly.

        No salary, or one in another currency, counts as missing.
        """
        pay = posting.salary
        if pay is None or pay.currency != wanted.currency or (pay.max is None and pay.min is None):
            return self._decide(None, wanted.if_missing)
        top = pay.max if pay.max is not None else pay.min
        reaches = top * self.YEARLY[pay.period] >= wanted.amount * self.YEARLY[wanted.period]
        return self._decide(reaches, wanted.if_missing)
