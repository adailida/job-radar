"""Postings and jobs: what the sources say about an opening, and the jobs merged from them."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from job_radar.models.llm import Classification, Extraction
from job_radar.models.model import Model


class RawPage(Model):
    """One page of results as a job board returned it, before it is parsed."""

    source: str  # "getro", "jobspipe"
    page: int  # 1 for the first page
    body: str  # the response text, unchanged


class WorkMode(StrEnum):
    """Where the work happens, as the posting states it."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class Period(StrEnum):
    """Time unit a salary is quoted in, so ranges compare like for like."""

    YEAR = "year"
    MONTH = "month"
    HOUR = "hour"


class Location(Model):
    """One place a posting names: the source's wording, plus codes when known."""

    text: str  # as the source wrote it
    country: str | None = None  # ISO 3166 code: "US"
    region: str | None = None  # ISO 3166-2 code: "US-NY"


class Salary(Model):
    """Pay range as posted. Either end may be missing."""

    min: Decimal | None = None
    max: Decimal | None = None
    currency: str
    period: Period
    text: str | None = None  # original wording


class Posting(Model):
    """What one source says about one opening.

    The common shape every source's data is converted into; nothing after the
    source sees the source's own format.
    """

    source: str  # "jobspipe", "getro"
    source_id: str  # id inside that source
    title: str
    company: str
    locations: tuple[Location, ...]
    work_mode: WorkMode
    salary: Salary | None = None
    url: str  # link to the posting
    posted_at: date | None = None
    description: str  # plain text, no HTML

    @property
    def key(self) -> str:
        """Id of this posting, unique across sources: source name plus the source's own id."""
        return f"{self.source}:{self.source_id}"


class Job(Model):
    """One real opening, after postings that describe it are merged across sources.

    Its id stays the same in every run that finds the opening again, from any source.
    """

    id: str
    keys: tuple[str, ...]  # identity keys that tie postings to this job
    postings: tuple[Posting, ...]  # primary first; the report shows its fields
    first_seen: date  # date of the run that first saw it
    classification: Classification | None = None  # labels, once classified; None when it failed
    extraction: Extraction | None = None  # requirements, once extracted; None when it failed


class Match(Model):
    """Which of the user's searches one job satisfies."""

    job_id: str
    searches: tuple[str, ...]  # search names
