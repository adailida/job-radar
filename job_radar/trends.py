"""How the market for the user's searches moves from one period to the next."""

import statistics
from calendar import monthrange
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable

from job_radar.history import RunHistory
from job_radar.model import (
    Job,
    Period,
    RunConfig,
    Seniority,
    TrendChange,
    TrendNote,
    TrendPeriod,
    Trends,
    Window,
    WorkMode,
)
from job_radar.seen import SeenJobs


class RunJobs:
    """One run as trends see it: its window, what it searched for, and its matched jobs.

    Immutable once made; holds no state beyond what it was given.
    """

    def __init__(self, window: Window, config: RunConfig | None, jobs: Sequence[Job]) -> None:
        """Keep the run's window, its searches and sources (None when unknown), and its jobs."""
        self.window = window
        self.config = config
        self.jobs = tuple(jobs)


class TrendBuilder:
    """Works out the trend periods, their figures, the change and the notes, from runs.

    A job counts in the period of its trend date: the earliest posted date of
    its postings, else the day it was first seen. A period's covered days are
    those inside some run's window; a period with fewer covered days than it
    has is partial, and postings are compared per covered day, so a gap doesn't
    look like a market drop. Shares leave out jobs that don't say. Only periods
    with a covered day are shown, the last six. Stateless: holds only the
    period kind and how many periods to show.
    """

    YEARLY = {Period.YEAR: Decimal(1), Period.MONTH: Decimal(12), Period.HOUR: Decimal(2080)}
    MODES = (WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE)
    LOW_SAMPLE = 20

    def __init__(self, period: str, shown: int = 6) -> None:
        """Keep the period kind (week, month or quarter) and how many periods to show."""
        self._period = period
        self._shown = shown

    def build(self, runs: Sequence[RunJobs]) -> Trends:
        """The trends for these runs, oldest first; a job in several runs counts once."""
        covered = {day for run in runs for day in self._days(run.window.start, run.window.end)}
        jobs: dict[str, Job] = {}
        for run in sorted(runs, key=lambda r: r.window.end):
            for job in run.jobs:
                jobs.setdefault(job.id, job)
        starts = sorted({self.period_of(day)[0] for day in covered})[-self._shown :]
        periods = [self._period_figures(start, covered, jobs.values()) for start in starts]
        return Trends(
            period=self._period,
            periods=tuple(periods),
            change=self._change(periods),
            notes=self._notes(runs, periods[0].start if periods else None),
            low_sample=self.LOW_SAMPLE,
        )

    def period_of(self, day: date) -> tuple[date, date]:
        """The first and last day of the period a day falls in."""
        if self._period == "week":
            start = day - timedelta(days=day.weekday())
            return start, start + timedelta(days=6)
        if self._period == "quarter":
            first_month = 3 * ((day.month - 1) // 3) + 1
            last_month = first_month + 2
            end = date(day.year, last_month, monthrange(day.year, last_month)[1])
            return date(day.year, first_month, 1), end
        return day.replace(day=1), day.replace(day=monthrange(day.year, day.month)[1])

    @staticmethod
    def trend_date(job: Job) -> date:
        """The day a job counts on: its earliest posted date, else the day it was first seen."""
        posted = [posting.posted_at for posting in job.postings if posting.posted_at]
        return min(posted) if posted else job.first_seen

    def _period_figures(self, start: date, covered: set[date], jobs: Iterable[Job]) -> TrendPeriod:
        """The figures for the period that starts on this day."""
        end = self.period_of(start)[1]
        days = sum(1 for day in self._days(start, end) if day in covered)
        inside = [job for job in jobs if start <= self.trend_date(job) <= end]
        postings = [job.postings[0] for job in inside]
        modes = [p.work_mode for p in postings if p.work_mode in self.MODES]
        pay = sorted(m for p in postings if (m := self._yearly_usd(p.salary)) is not None)
        levels = [
            job.classification.seniority
            for job in inside
            if job.classification and job.classification.seniority is not Seniority.UNKNOWN
        ]
        quartiles = self._quartiles(pay)
        return TrendPeriod(
            start=start,
            end=end,
            covered_days=days,
            postings=len(inside),
            per_day=len(inside) / days if days else None,
            work_modes=self._shares([m.value for m in modes], [m.value for m in self.MODES]),
            work_mode_base=len(modes),
            work_mode_unknown=len(postings) - len(modes),
            salary_median=quartiles[1],
            salary_p25=quartiles[0],
            salary_p75=quartiles[2],
            salary_base=len(pay),
            salary_listed=(
                sum(1 for p in postings if p.salary) / len(postings) if postings else None
            ),
            seniority=self._shares([s.value for s in levels], [s.value for s in Seniority]),
            seniority_base=len(levels),
            seniority_unknown=len(inside) - len(levels),
        )

    def _yearly_usd(self, salary) -> int | None:
        """The yearly midpoint of a USD pay range, or None for another currency or no pay."""
        if salary is None or salary.currency != "USD":
            return None
        ends = [amount for amount in (salary.min, salary.max) if amount is not None]
        if not ends:
            return None
        return int(sum(ends) / len(ends) * self.YEARLY[salary.period])

    @staticmethod
    def _quartiles(values: list[int]) -> tuple[int | None, int | None, int | None]:
        """The 25th percentile, median and 75th percentile of sorted values, or None for none."""
        if not values:
            return None, None, None
        if len(values) == 1:
            return values[0], values[0], values[0]
        low, middle, high = statistics.quantiles(values, n=4, method="inclusive")
        return round(low), round(middle), round(high)

    @staticmethod
    def _shares(values: list[str], order: Sequence[str]) -> dict[str, float]:
        """The share of each value that occurs, in the given order."""
        if not values:
            return {}
        return {key: values.count(key) / len(values) for key in order if key in values}

    @staticmethod
    def _days(start: date, end: date) -> Iterable[date]:
        """Every day from start to end, both included."""
        return (start + timedelta(days=n) for n in range((end - start).days + 1))

    def _change(self, periods: list[TrendPeriod]) -> TrendChange | None:
        """The latest period against the last complete period before it, if there is one."""
        if len(periods) < 2:
            return None
        latest = periods[-1]
        base = next((p for p in reversed(periods[:-1]) if not p.partial), None)
        if base is None:
            return None
        return TrendChange(
            against=base.start,
            per_day=self._percent(latest.per_day, base.per_day),
            work_modes=self._points(latest.work_modes, base.work_modes),
            salary_median=self._percent(latest.salary_median, base.salary_median),
            seniority=self._points(latest.seniority, base.seniority),
        )

    @staticmethod
    def _percent(new: float | None, old: float | None) -> float | None:
        """The change from old to new, in percent; None when either is missing or old is 0."""
        if new is None or not old:
            return None
        return (new - old) / old * 100

    @staticmethod
    def _points(new: dict[str, float], old: dict[str, float]) -> dict[str, float]:
        """The change in each share, in percentage points, for shares in either period."""
        keys = [*new, *(key for key in old if key not in new)]
        return {key: (new.get(key, 0.0) - old.get(key, 0.0)) * 100 for key in keys}

    @staticmethod
    def _notes(runs: Sequence[RunJobs], since: date | None) -> tuple[TrendNote, ...]:
        """What changed in searches or sources between runs, from the first period shown on."""
        known = sorted((r for r in runs if r.config is not None), key=lambda r: r.window.end)
        notes = []
        for before, after in zip(known, known[1:], strict=False):
            changes = TrendBuilder._differences(before.config, after.config)
            if changes and (since is None or after.window.end >= since):
                notes.append(TrendNote(day=after.window.end, changes=changes))
        return tuple(notes)

    @staticmethod
    def _differences(old: RunConfig, new: RunConfig) -> tuple[str, ...]:
        """The sources and searches added, removed or changed from one run to the next."""
        changes = [f"added source {s}" for s in new.sources if s not in old.sources]
        changes += [f"removed source {s}" for s in old.sources if s not in new.sources]
        before = {search.name: search for search in old.searches}
        after = {search.name: search for search in new.searches}
        changes += [f"added search {name}" for name in after if name not in before]
        changes += [f"removed search {name}" for name in before if name not in after]
        changes += [
            f"changed search {name}"
            for name in after
            if name in before and after[name] != before[name]
        ]
        return tuple(changes)


@runtime_checkable
class KeptJobs(Protocol):
    """Read-only view of the jobs this run keeps: its matched jobs."""

    def kept[M](self, kind: type[M]) -> list[M]:
        """The kept step's output, read as this kind."""
        ...


@runtime_checkable
class TrendSource(Protocol):
    """Gives the report its market trends section."""

    def trends(self) -> Trends:
        """The trends, from earlier runs and this one."""
        ...


@runtime_checkable
class RunsSource(Protocol):
    """Gives the runs the market sections look at: every completed run, then this one."""

    def runs(self) -> list[RunJobs]:
        """The runs, each with its window, searches and matched jobs."""
        ...


class MarketRuns:
    """Reads every completed run's matched jobs, and adds this run's, for the market sections.

    Completed runs' matched jobs come from what each kept; this run's from
    its kept output, since it hasn't completed yet. Free: nothing is fetched
    and no model is asked. Stateless: holds only where runs and their kept
    jobs are read, and this run's jobs, window and searches.
    """

    def __init__(
        self,
        history: RunHistory,
        seen: SeenJobs,
        this_run: KeptJobs,
        window: Window,
        config: RunConfig,
    ) -> None:
        """Keep the run history and the jobs each run kept, and this run's jobs and facts."""
        self._history = history
        self._seen = seen
        self._this_run = this_run
        self._window = window
        self._config = config

    def runs(self) -> list[RunJobs]:
        """Every completed run, oldest last as history lists them, then this run."""
        runs = [
            RunJobs(run.window, run.config, self._seen.jobs(run.id))
            for run in self._history.runs()
            if run.completed
        ]
        runs.append(RunJobs(self._window, self._config, self._this_run.kept(Job)))
        return runs


class MarketTrends:
    """Has the trends worked out over the runs the market sections look at.

    Stateless: holds only where the runs come from and the builder.
    """

    def __init__(self, runs: RunsSource, builder: TrendBuilder) -> None:
        """Keep where the runs come from and the builder."""
        self._runs = runs
        self._builder = builder

    def trends(self) -> Trends:
        """The trends over every completed run, plus this run."""
        return self._builder.build(self._runs.runs())
