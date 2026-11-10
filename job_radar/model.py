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


class Seniorities(_Criterion):
    """The levels wanted: a job matches if its seniority is any of them. Unknown is missing."""

    values: tuple[Seniority, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _known_levels(self) -> Self:
        """Unknown is what a missing level is, not a level to ask for."""
        if Seniority.UNKNOWN in self.values:
            raise ValueError("ask for levels such as senior or lead; unknown is if_missing's job")
        return self


class Domains(_Criterion):
    """The domains wanted, by name from the settings: a job matches if its domain is any of them."""

    values: tuple[str, ...] = Field(min_length=1)


class Search(Model):
    """One named search: criteria a job must meet together. An unset criterion lets every job by."""

    # TODO(task 11c): keywords in the description, checked after the describe step.
    name: str
    roles: tuple[str, ...] = ()  # the title contains any, as whole words
    exclude_titles: tuple[str, ...] = ()  # the title contains none, as whole words
    work_mode: WorkModes | None = None
    locations: Places | None = None
    min_salary: MinSalary | None = None
    seniority: Seniorities | None = None  # checked once the job is classified
    domains: Domains | None = None  # checked once the job is classified


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
    alerts: tuple[str, ...] = ()  # the run's warnings, one line each, for the terminal


class StepCount(Model):
    """How many items one finished step of a run produced."""

    step: str
    count: int


class SourceCount(Model):
    """How many postings one source gave in a run."""

    source: str  # the source's name in the data: "getro", "jobspipe"
    postings: int


class SourceSummary(Model):
    """One source in the report's header: its name for people, what it gave and what it cost."""

    source: str  # the source's name in the data: "getro"
    name: str  # its name for people: "Fast Forward"
    postings: int
    credits: int | None = None  # what a paid source charged; None for a free one
    skipped: bool = False  # a paid source the user chose to skip this run


class AlertCode(StrEnum):
    """What kind of problem a warning is about: the run went on despite it."""

    SOURCE_FAILED = "source_failed"  # a source raised after its retries
    SOURCE_EMPTY = "source_empty"  # a source returned no postings
    SOURCE_SKIPPED = "source_skipped"  # the user left a paid source out at the cost check
    NO_NEW_JOBS = "no_new_jobs"  # no new job matched the searches
    BUDGET_REACHED = "budget_reached"  # a paid source used what its monthly budget had left
    CREDITS_LOW = "credits_low"  # a paid source has fewer credits left than the setting
    LLM_FAILED = "llm_failed"  # the LLM couldn't label, read or rank some jobs
    LLM_PENDING = "llm_pending"  # the usage limit carried jobs over to the next run
    LLM_CAPPED = "llm_capped"  # jobs over the LLM cap were carried over to the next run
    GAPS_SKIPPED = "gaps_skipped"  # some requirements weren't compared with the CV
    RUN_UNREADABLE = "run_unreadable"  # an earlier run folder can't be read
    KEPT_JOBS_UNREADABLE = "kept_jobs_unreadable"  # an earlier run's kept jobs can't be read


class Alert(Model):
    """A problem from the run that didn't stop it: shown at the top of the report and at the end."""

    code: AlertCode
    message: str  # one sentence, as the user reads it


class Opening(Model):
    """One new matched job in the report's new openings, with its score when it was recommended."""

    job: Job
    score: int | None = None  # None when it wasn't among the recommended jobs


class OpeningGroup(Model):
    """A heading in the new openings: a job type or a domain, and the jobs under it.

    Grouped by both, a job type's group holds a group per domain instead of jobs.
    """

    name: str  # a name from the settings, "Other" or "Not labelled"
    openings: tuple[Opening, ...] = ()  # newest posted first
    groups: tuple["OpeningGroup", ...] = ()  # the groups inside it, when grouped by both

    @property
    def size(self) -> int:
        """How many jobs it holds, inside its groups included."""
        return len(self.openings) + sum(group.size for group in self.groups)


class ReportContent(Model):
    """Everything a report says, decided before it is formatted.

    The renderer only formats it, so another format is a new renderer and
    the content logic is tested without Markdown.
    """

    run: str  # the run's folder name, e.g. "2026-11-09T13-58-11"
    window: Window
    not_covered: Window | None = None  # days a long break left out, before the window
    sources: tuple[SourceSummary, ...] = ()  # the run's sources, in the order they were fetched
    alerts: tuple[Alert, ...] = ()
    min_score: int  # the lowest score a recommended job may have
    recommendations: tuple[Recommendation, ...]  # best first
    openings: tuple[OpeningGroup, ...] = ()  # this run's new matched jobs, by group
    funnel: tuple[StepCount, ...]  # each finished step and its count, in run order
    spends: tuple["Spend", ...] = ()  # what each paid source spent
    carried_over: int = 0  # jobs carried over to the next run by the usage limit or the LLM cap
    trends: "Trends | None" = None  # the market trends section
    asks: "Asks | None" = None  # the what employers ask for section
    gaps: "Gaps | None" = None  # the experience to gain section

    @property
    def new_openings(self) -> int:
        """How many new matched jobs the report lists."""
        return sum(group.size for group in self.openings)


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
    not_covered: Window | None = None  # days a long break left out, before the window
    completed: bool
    steps: tuple[StepCount, ...]  # each finished step and its count, in run order
    config: "RunConfig | None" = None  # what it searched for and where; None for older runs


class SpendPlan(Model):
    """What a paid source expects a run to cost, and the limits to check it against."""

    source: str
    estimate: int  # the most the run's searches can cost: their match counts added up
    estimated: bool  # False when the source couldn't count, and the estimate is the per-run max
    credits_left: int
    per_run_max: int
    budget_left: int  # what the monthly budget still allows; the credits left on a one-time grant


class SpendDecision(StrEnum):
    """How a paid source's spend was agreed."""

    AUTO = "auto"  # within every limit
    APPROVED = "approved"  # over a limit, and the user said go ahead
    SKIPPED = "skipped"  # the user chose to leave the source out of this run
    FAILED = "failed"  # the source failed at the cost check, so it is left out of this run


class Approval(Model):
    """The spend agreed for one paid source before anything is fetched."""

    source: str
    estimate: int
    decision: SpendDecision
    cap: int  # the most the fetch may spend: the estimate plus 10%, within the credits left
    credits_before: int  # 0 when the cost check failed
    budget_left: int | None = None  # what the monthly budget still allowed; None in older runs
    failure: str | None = None  # why the cost check failed, when it did


class PaidFetch(Model):
    """What a paid source fetched and what it cost."""

    pages: tuple[RawPage, ...]
    charged: int
    credits_left: int


class Spend(Model):
    """One paid source's spend in a run: what was agreed and what it cost."""

    approval: Approval
    charged: int = 0
    credits_after: int | None = None  # None when the source was skipped


class RunConfig(Model):
    """What a run searched for and where: kept in its manifest, so later trends can tell."""

    searches: tuple[Search, ...]
    sources: tuple[str, ...]  # the boards it fetched from, by name


class TrendPeriod(Model):
    """The figures for one trend period: a week, a month or a quarter.

    Shares are fractions from 0 to 1. Each figure keeps how many jobs it rests
    on, so a thin one can be marked as a low sample.
    """

    start: date
    end: date
    covered_days: int  # days of the period inside some run's window
    postings: int  # matched jobs dated in the period
    per_day: float | None  # postings per covered day; None with no covered day
    work_modes: dict[str, float]  # remote, hybrid, onsite: share of jobs that say
    work_mode_base: int  # jobs that say their work mode
    work_mode_unknown: int
    salary_median: int | None  # yearly USD, from the midpoint of each range
    salary_p25: int | None
    salary_p75: int | None
    salary_base: int  # jobs with a USD salary
    salary_listed: float | None  # share of jobs listing any salary
    seniority: dict[str, float]  # each level: share of jobs with a known level
    seniority_base: int  # jobs with a known level
    seniority_unknown: int  # jobs with no level, or no labels

    @property
    def days(self) -> int:
        """How many days the period has."""
        return (self.end - self.start).days + 1

    @property
    def partial(self) -> bool:
        """Whether some of its days fell outside every run's window."""
        return self.covered_days < self.days


class TrendChange(Model):
    """The latest period against the last complete one before it."""

    against: date  # the start of the period compared with
    per_day: float | None  # percent change in postings per covered day
    work_modes: dict[str, float]  # change in each share, in points
    salary_median: float | None  # percent change
    seniority: dict[str, float]  # change in each share, in points


class TrendNote(Model):
    """A change to what runs searched for or where, so a jump isn't read as the market."""

    day: date  # the last day of the run that changed it
    changes: tuple[str, ...]  # "added source jobspipe", "changed search remote-us"


class Trends(Model):
    """The market trends section: recent periods, the change, and notes."""

    period: str  # week, month or quarter
    periods: tuple[TrendPeriod, ...]  # oldest first, at most six
    change: TrendChange | None  # None when there's nothing complete to compare with
    notes: tuple[TrendNote, ...]
    low_sample: int  # a figure resting on fewer jobs than this is marked


class AskRow(Model):
    """One requirement in the what employers ask for section, with where it came from."""

    type: RequirementType
    name: str  # the most common way postings spell it
    jobs: int  # jobs in the window that ask for it
    share: float  # of the jobs with requirements in the window, 0 to 1
    change: float | None  # in points against the window before; None with nothing to compare
    job_ids: tuple[str, ...]  # the jobs it came from, so it can be traced
    median_years: float | None = None  # for years rows: the median number asked


class Asks(Model):
    """The what employers ask for section: the top requirements of each type in a window."""

    window: Window  # the rolling window, ending on the run's last day
    previous: Window  # the window of the same length before it
    jobs: int  # jobs with requirements in the window
    previous_jobs: int  # jobs with requirements in the window before; 0 means no change yet
    rows: tuple[AskRow, ...]  # by type, then most asked first
    low_sample: int  # fewer jobs than this in the window is a low sample


class GapStatus(StrEnum):
    """How far the CV shows a requirement."""

    COVERED = "covered"
    PARTLY = "partly"  # some of it, such as fewer years than asked or a related tool
    MISSING = "missing"


class GapJudgment(Model):
    """How one requirement compares with the CV, and how to gain it when it's a gap."""

    status: GapStatus
    reason: str  # one line
    suggestion: str | None = None  # how to gain it; only for some gaps
    prompt_version: str


class GapRow(Model):
    """One requirement in the experience to gain section: what employers ask, against the CV."""

    requirement: AskRow
    status: GapStatus
    reason: str
    suggestion: str | None  # only for the most asked gaps


class GapSkip(StrEnum):
    """Why some requirements weren't compared with the CV this run."""

    FAILED = "failed"  # the LLM gave no usable answer, or no answer at all
    USAGE_LIMIT = "usage_limit"  # the LLM's usage limit is reached


class Gaps(Model):
    """The experience to gain section: what employers ask for, against the CV."""

    rows: tuple[GapRow, ...]  # gaps (missing, partly) most asked first, then covered ones
    skipped: GapSkip | None = None  # why some requirements weren't compared, if any
    not_compared: int = 0  # requirements left out because they weren't compared


ReportContent.model_rebuild()
RunSummary.model_rebuild()
