"""A run's own records: its windows, counts, searches, what the filter dropped, its summary."""

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
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


class WindowReason(StrEnum):
    """Why a source's window starts where it does."""

    FIRST_RUN = "first_run"  # no completed run covered the source yet: the whole lookback
    SINCE_LAST_RUN = "since_last_run"  # picks up where the last completed run ended
    CATCHING_UP = "catching_up"  # the last completed run missed it: from where it was covered
    CAPPED = "capped"  # it was last covered before the lookback: the lookback only


class SourceWindow(Model):
    """One source's dates in a run, why they start there, and whether the run covered them.

    A source is covered once the fetch step got all it had for those dates;
    a source that failed, was skipped or came back empty although its count
    said otherwise is not, so the next run fetches its dates again.
    """

    source: str  # the source's name in the data: "getro", "jobspipe"
    window: Window
    reason: WindowReason | None = None  # None when the run predates it (resumed older runs)
    not_covered: Window | None = None  # days the lookback left out, before its window
    covered: bool = False  # set by the fetch step


class RunWindows(Model):
    """The dates a run fetches: each source's own, and the window that spans them all."""

    window: Window  # from the earliest source's start to the run's last day
    not_covered: Window | None = None  # days the lookback left out, when every source shares them
    sources: tuple[SourceWindow, ...] = ()  # empty for runs from before sources had their own

    @classmethod
    def spanning(cls, sources: Sequence[SourceWindow]) -> Self:
        """The run's windows from each source's: the run's window spans all of them."""
        if not sources:
            raise ValueError("a run needs at least one source")
        window = Window(
            start=min(source.window.start for source in sources),
            end=max(source.window.end for source in sources),
        )
        gaps = {source.not_covered for source in sources}
        return cls(
            window=window,
            not_covered=next(iter(gaps)) if len(gaps) == 1 else None,
            sources=tuple(sources),
        )

    def of(self, source: str) -> Window:
        """A source's own window; the run's window for a source it has none for."""
        found = next((s for s in self.sources if s.source == source), None)
        return found.window if found is not None else self.window

    def differ(self) -> bool:
        """Whether the sources fetch different dates, or the same ones for different reasons."""
        return len({(source.window, source.reason) for source in self.sources}) > 1


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
    """One run as the run history sees it: its id, windows, whether it completed, its steps."""

    id: str  # the run folder's name: when it started, e.g. "2026-11-09T14-52-11"
    window: Window  # spans every source's window
    not_covered: Window | None = None  # days a long break left out, before the window
    completed: bool
    steps: tuple[StepCount, ...]  # each finished step and its count, in run order
    config: "RunConfig | None" = None  # what it searched for and where; None for older runs
    sources: tuple[SourceWindow, ...] = ()  # each source's dates and coverage; () in older runs

    def windows(self) -> RunWindows:
        """The run's windows, to resume it with the same dates for each source."""
        return RunWindows(window=self.window, not_covered=self.not_covered, sources=self.sources)

    def covered(self, source: str) -> Window | None:
        """The dates this run covered in full for a source, or None when it didn't.

        A failed run covers nothing. A run from before sources had their own
        dates covers its window for every source it lists, or for every source
        when it lists none.
        """
        if not self.completed:
            return None
        if not self.sources:
            listed = self.config is None or source in self.config.sources
            return self.window if listed else None
        found = next((s for s in self.sources if s.source == source), None)
        return found.window if found is not None and found.covered else None


RunSummary.model_rebuild()
