"""A run's own records: its window, counts, searches, what the filter dropped, its summary."""

from datetime import date
from typing import Self

from pydantic import model_validator

from job_radar.models.model import Model
from job_radar.models.posting import Job
from job_radar.models.search import Search


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


class StepCount(Model):
    """How many items one finished step of a run produced."""

    step: str
    count: int


class SourceCount(Model):
    """How many postings one source gave in a run."""

    source: str  # the source's name in the data: "getro", "jobspipe"
    postings: int


class RunConfig(Model):
    """What a run searched for and where: kept in its manifest, so later trends can tell."""

    searches: tuple[Search, ...]
    sources: tuple[str, ...]  # the boards it fetched from, by name


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


RunSummary.model_rebuild()
