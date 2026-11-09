"""Domain models: the records a run produces, saves and reads back.

Each record is created once by one step of a run and never changed after. Every
model is frozen and stores collections as tuples, so nothing can modify it in place.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    """Base for all domain models: immutable, and rejects fields it doesn't know.

    Rejecting unknown fields means a typo in saved data fails loudly on load
    instead of being silently dropped.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


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


class Seniority(StrEnum):
    """Level of a role, as judged from the posting."""

    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"  # staff, principal, tech lead
    MANAGER = "manager"
    EXECUTIVE = "executive"  # director and above
    UNKNOWN = "unknown"


class RequirementType(StrEnum):
    """Kind of thing a posting asks for."""

    SKILL = "skill"
    TOOL = "tool"
    CERTIFICATION = "certification"
    YEARS = "years"


class Window(Model):
    """The dates a run fetches postings for, both ends included."""

    start: date
    end: date

    @model_validator(mode="after")
    def _start_not_after_end(self) -> Self:
        """Reject a window that ends before it starts: always a bug in the caller."""
        if self.start > self.end:
            raise ValueError(f"start {self.start} is after end {self.end}")
        return self


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


class RawPage(Model):
    """One page of results as a job board returned it, before it is parsed."""

    source: str  # "getro", "jobspipe"
    page: int  # 1 for the first page
    body: str  # the response text, unchanged


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


class Classification(Model):
    """Labels for one job, used to match it against searches and group it in the report."""

    job_id: str
    seniority: Seniority
    job_type: str | None = None  # a job type from settings, "Other", or None when unclear
    domain: str | None = None  # a domain from settings, "Other", or None when unclear
    sector: str | None = None  # free label, for an informational breakdown
    prompt_version: str  # prompt that produced the labels


class Requirement(Model):
    """One thing a posting asks for: a skill, tool, certification or years of experience."""

    type: RequirementType
    name: str  # normalized: "Python", "CISSP"
    years: int | None = None  # for type years: 5 in "5+ years of Python"


class Extraction(Model):
    """The requirements found in one matched job's posting."""

    job_id: str
    requirements: tuple[Requirement, ...]
    prompt_version: str  # prompt that produced the requirements


class Match(Model):
    """Which of the user's searches one job satisfies."""

    job_id: str
    searches: tuple[str, ...]  # search names


class Search(Model):
    """One named search: criteria a job must meet together."""

    # TODO(task 11): add locations, work mode, keywords, salary and if_missing.
    name: str
    roles: tuple[str, ...]


class SearchCriteria(Model):
    """All of the user's searches. A job is wanted if it matches any of them."""

    searches: tuple[Search, ...]


class CandidateProfile(Model):
    """What a good job is for the user: their CV and their ideal job in their own words."""

    cv: str  # text taken from the CV file
    preferences: str  # free text


class Recommendation(Model):
    """One job recommended for the user, with how well it fits and why."""

    job: Job
    score: int = Field(ge=0, le=100)
    reason: str  # one line


class Report(Model):
    """The finished report of a run: where to find it and what it found, in one line."""

    location: str  # e.g. a file path
    summary: str  # e.g. "12 recommendations from 340 postings"


class StepCount(Model):
    """How many items one finished step of a run produced."""

    step: str
    count: int


class ReportContent(Model):
    """Everything a report says, decided before it is formatted.

    The renderer only formats it, so another format is a new renderer and
    the content logic is tested without Markdown.
    """

    run: str  # the run's folder name, e.g. "2026-11-09T13-58-11"
    window: Window
    min_score: int  # the lowest score a recommended job may have
    recommendations: tuple[Recommendation, ...]  # best first
    funnel: tuple[StepCount, ...]  # each finished step and its count, in run order
