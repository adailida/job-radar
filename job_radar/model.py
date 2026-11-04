"""Domain models (design section 3).

Each type is made by one stage and never changed after. Models are frozen and
store collections as tuples, so nothing can modify them in place.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator


class Model(BaseModel):
    """Base for every model that crosses a boundary: frozen, unknown fields rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class WorkMode(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class Period(StrEnum):
    YEAR = "year"
    MONTH = "month"
    HOUR = "hour"


class Seniority(StrEnum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"  # staff, principal, tech lead
    MANAGER = "manager"
    EXECUTIVE = "executive"  # director and above
    UNKNOWN = "unknown"


class RequirementType(StrEnum):
    SKILL = "skill"
    TOOL = "tool"
    CERTIFICATION = "certification"
    YEARS = "years"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Decision(StrEnum):
    AUTO = "auto"
    APPROVED = "approved"
    SKIPPED = "skipped"


class Window(Model):
    """Dates a run covers, both ends included."""

    start: date
    end: date

    @model_validator(mode="after")
    def _start_not_after_end(self) -> Self:
        if self.start > self.end:
            raise ValueError(f"start {self.start} is after end {self.end}")
        return self


class Location(Model):
    text: str  # as the source wrote it
    country: str | None = None  # ISO 3166 code when known: "US"
    region: str | None = None  # ISO 3166-2 code when known: "US-NY"


class Salary(Model):
    min: Decimal | None = None
    max: Decimal | None = None
    currency: str
    period: Period  # so ranges compare like for like
    text: str | None = None  # original wording


class Posting(Model):
    """What one source says about one opening. Built by the adapter."""

    source: str  # "jobspipe", "getro"
    source_id: str  # id inside that source
    title: str
    company: str
    locations: tuple[Location, ...]
    work_mode: WorkMode
    salary: Salary | None = None
    url: str  # link to the posting
    posted_at: date | None = None
    description: str  # plain text; the adapter strips HTML

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


class Job(Model):
    """One opening after dedupe, backed by one or more postings."""

    id: str  # stable across runs (section 8)
    keys: tuple[str, ...]  # identity keys: posting, ATS, fuzzy
    postings: tuple[Posting, ...]  # primary first; the report shows its fields
    first_seen: date  # date of the run that first saw it


class Classification(Model):
    job_id: str
    seniority: Seniority
    job_type: str | None = None  # a job type from settings, "Other", or None when unclear
    domain: str | None = None  # a domain from settings, "Other", or None when unclear
    sector: str | None = None  # free label, for the informational breakdown
    prompt_version: str


class Requirement(Model):
    type: RequirementType
    name: str  # normalized: "Python", "CISSP"
    years: int | None = None  # for type years: 5 in "5+ years of Python"


class Extraction(Model):
    job_id: str
    requirements: tuple[Requirement, ...]
    prompt_version: str


class Match(Model):
    job_id: str
    searches: tuple[str, ...]  # names of the searches it matched


class Search(Model):
    """One named search. Minimal for now; section 7 adds the other criteria (task 8)."""

    name: str
    roles: tuple[str, ...]


class SearchCriteria(Model):
    searches: tuple[Search, ...]


class SourceResult(Model):
    source: str
    queries: tuple[dict[str, Any], ...]  # what was sent, one per search
    fetched: int
    estimate: int | None = None  # paid sources: sum of counts (section 12)
    credits_before: int | None = None
    credits_after: int | None = None
    credits_spent: int | None = None  # None for free sources
    decision: Decision | None = None
    error: str | None = None


class Run(Model):
    id: str  # start time, e.g. "2026-11-03T14-05"
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    window: Window
    criteria: SearchCriteria  # snapshot, to note criteria changes between periods
    sources: tuple[SourceResult, ...] = ()
