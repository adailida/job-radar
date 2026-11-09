"""Domain models: the records a run produces, saves and reads back.

Each record is created once by one step of a run and never changed after. Every
model is frozen and stores collections as tuples, so nothing can modify it in place.
"""

import re
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


class IfMissing(StrEnum):
    """What a criterion does with a job that doesn't say: keep it or drop it."""

    KEEP = "keep"
    DROP = "drop"


class _Criterion(Model):
    """Base for criteria a posting may not say anything about.

    Written in full (`{values: [...], if_missing: drop}`) or short, as just the
    list of values, which keeps jobs that don't say.
    """

    if_missing: IfMissing = IfMissing.KEEP

    @model_validator(mode="before")
    @classmethod
    def _short_form(cls, data: object) -> object:
        """Read a bare list as the values, keeping jobs that don't say."""
        return {"values": data} if isinstance(data, list | tuple) else data


class WorkModes(_Criterion):
    """The work modes wanted: a job matches if it has any of them."""

    values: tuple[WorkMode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _known_modes(self) -> Self:
        """Unknown is what a missing work mode is, not a mode to ask for."""
        if WorkMode.UNKNOWN in self.values:
            raise ValueError("work modes are remote, hybrid or onsite")
        return self


class Places(_Criterion):
    """The places wanted, as ISO codes: `US` is anywhere in the US, `US-WA` is Washington only."""

    values: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _iso_codes(self) -> Self:
        """Each value is a country code, optionally with a region: `US`, `US-WA`."""
        bad = [v for v in self.values if not re.fullmatch(r"[A-Z]{2}(-[A-Z0-9]{1,3})?", v)]
        if bad:
            raise ValueError(f"not ISO codes like US or US-WA: {', '.join(bad)}")
        return self


class MinSalary(_Criterion):
    """The lowest pay wanted. A job meets it if the top of its range does."""

    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    period: Period = Period.YEAR

    @model_validator(mode="before")
    @classmethod
    def _short_form(cls, data: object) -> object:
        """Read a bare number as a yearly amount in USD, keeping jobs that don't say."""
        return {"amount": data} if isinstance(data, int | float | str | Decimal) else data


class Search(Model):
    """One named search: criteria a job must meet together. An unset criterion lets every job by."""

    # TODO(task 11c): keywords in the description, checked after the describe step.
    name: str
    roles: tuple[str, ...] = ()  # the title contains any, as whole words
    exclude_titles: tuple[str, ...] = ()  # the title contains none, as whole words
    work_mode: WorkModes | None = None
    locations: Places | None = None
    min_salary: MinSalary | None = None


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


class DroppedJob(Model):
    """A job the filter dropped, and why: for each search, the first criterion it failed."""

    job: Job
    reasons: tuple[str, ...]  # "remote-us: work mode", one per search, in the searches' order


class DropList(Model):
    """What the filter dropped in one run, for the user to check for misses."""

    window: Window
    checked: int  # jobs the filter looked at
    kept: int
    before_window: int  # dropped for being posted before the window; not listed
    dropped: tuple[DroppedJob, ...]  # dropped by the searches


class RunSummary(Model):
    """One run as the run history sees it: its id, window, whether it completed, its steps."""

    id: str  # the run folder's name: when it started, e.g. "2026-11-09T14-52-11"
    window: Window
    completed: bool
    steps: tuple[StepCount, ...]  # each finished step and its count, in run order
