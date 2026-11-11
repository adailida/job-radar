"""What a report says, decided before it is formatted: its sections, alerts and openings."""

from datetime import date
from enum import StrEnum

from pydantic import Field

from job_radar.models.llm import GapStatus, RequirementType
from job_radar.models.model import Model
from job_radar.models.posting import Job
from job_radar.models.run import SourceWindow, StepCount, Window
from job_radar.models.spend import Spend


class Report(Model):
    """The finished report of a run: where to find it and what it found, in one line."""

    location: str  # e.g. a file path
    summary: str  # e.g. "12 recommendations from 340 postings"
    alerts: tuple[str, ...] = ()  # the run's warnings, one line each, for the terminal


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


class Recommendation(Model):
    """One job recommended for the user, with how well it fits and why."""

    job: Job
    score: int = Field(ge=0, le=100)
    reason: str  # one line


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
    window: Window  # spans every source's window
    not_covered: Window | None = None  # days a long break left out, before the window
    source_windows: tuple[SourceWindow, ...] = ()  # each source's own dates, when they differ
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
