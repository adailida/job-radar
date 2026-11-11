"""Which dates a run fetches postings for, agreed with the user before anything is fetched."""

from collections.abc import Mapping
from datetime import date, timedelta

from job_radar.models import Model, RunWindows, SourceWindow, Window, WindowReason
from job_radar.storage.run_history import RunHistory
from job_radar.utils.clock import Clock
from job_radar.utils.prompter import Prompter


class WindowPlan(Model):
    """A source's window, why it was chosen, and when it was last covered in full."""

    window: Window
    reason: WindowReason
    last_run: date | None = None  # the last day of the last completed run that covered it

    def not_covered(self) -> Window | None:
        """The days between the last covered run and this window, when the lookback cut them off."""
        if self.reason is not WindowReason.CAPPED or self.last_run is None:
            return None
        start, end = self.last_run + timedelta(days=1), self.window.start - timedelta(days=1)
        return Window(start=start, end=end) if start <= end else None


class WindowPlanner:
    """Decides the dates a source covers in a run, from where it was last covered and the lookback.

    A source starts one day before the last day of the last completed run
    that covered it in full. That day is fetched again because the run may
    have been early in it, and the day before because boards can list a
    posting a day after its date. Repeats are cheap, and recognising jobs
    already seen removes them. A source the newest completed run missed
    catches up from where it was last covered. Stateless: holds only the
    lookback.
    """

    MARGIN = timedelta(days=1)

    def __init__(self, lookback_days: int) -> None:
        """Keep how many days back a run may reach at most."""
        self._lookback = timedelta(days=lookback_days)

    def plan(self, today: date, last: Window | None, newest: date | None = None) -> WindowPlan:
        """A source's window today, given its window in the last run that covered it, if any.

        `newest` is the last day of the newest completed run: a source last
        covered before it is catching up.
        """
        earliest = today - self._lookback
        if last is None:
            return WindowPlan(
                window=Window(start=earliest, end=today), reason=WindowReason.FIRST_RUN
            )
        start = min(last.end - self.MARGIN, today)
        if start < earliest:
            return WindowPlan(
                window=Window(start=earliest, end=today),
                reason=WindowReason.CAPPED,
                last_run=last.end,
            )
        missed = newest is not None and last.end < newest
        return WindowPlan(
            window=Window(start=start, end=today),
            reason=WindowReason.CATCHING_UP if missed else WindowReason.SINCE_LAST_RUN,
            last_run=last.end,
        )


class WindowChooser:
    """Works out each source's window for a run and agrees them with the user.

    When every source picks up from a recent run, it says which dates it
    will fetch and goes ahead. When a source was never covered, or was last
    covered before the lookback, it asks first, since the run reaches back
    further than usual. When the sources' dates differ, it says each one's.
    Stateless: holds only what it reads from, the sources, and who it asks.
    """

    ASK = (WindowReason.FIRST_RUN, WindowReason.CAPPED)  # reach back further than usual
    ONE_LINE = (WindowReason.SINCE_LAST_RUN, WindowReason.CAPPED)  # said once when all share it

    def __init__(
        self,
        history: RunHistory,
        planner: WindowPlanner,
        prompter: Prompter,
        clock: Clock,
        sources: Mapping[str, str],
    ) -> None:
        """Keep where earlier runs are read from, the planner, the user, the clock, the sources.

        `sources` names the run's sources for people, by their name in the data.
        """
        self._history = history
        self._planner = planner
        self._prompter = prompter
        self._clock = clock
        self._sources = sources

    def choose(self) -> RunWindows | None:
        """Each source's window for the run, or None if the user said no."""
        today = self._clock.now().date()
        newest = self._history.last_window()
        newest_end = newest.end if newest is not None else None
        plans = {
            source: self._planner.plan(today, self._history.last_covered(source), newest_end)
            for source in self._sources
        }
        windows = RunWindows.spanning(
            [
                SourceWindow(
                    source=source,
                    window=plan.window,
                    reason=plan.reason,
                    not_covered=plan.not_covered(),
                )
                for source, plan in plans.items()
            ]
        )
        self._tell(plans, windows.window, first=newest is None)
        if all(plan.reason not in self.ASK for plan in plans.values()):
            return windows
        return windows if self._prompter.confirm("Continue?") else None

    def _tell(self, plans: Mapping[str, WindowPlan], window: Window, first: bool) -> None:
        """Say which dates the run will fetch and why: once when the sources share them.

        `first` is whether no run has completed yet.
        """
        shared = set(plans.values())
        if len(shared) == 1:
            plan = shared.pop()
            if first or plan.reason in self.ONE_LINE:
                self._prompter.tell(self._describe(plan))
                return
        self._prompter.tell(f"Fetching {self._dates(window)}, each source on its own:")
        for source, plan in plans.items():
            self._prompter.tell(f"- {self._sources[source]}: {self._each(plan)}")

    def _describe(self, plan: WindowPlan) -> str:
        """Say which dates the run will fetch, and why those, when every source shares them."""
        dates = self._dates(plan.window)
        days = (plan.window.end - plan.window.start).days
        match plan.reason:
            case WindowReason.FIRST_RUN:
                return f"No earlier runs. Fetching the last {days} days: {dates}."
            case WindowReason.CAPPED:
                return (
                    f"The last run was on {self._day(plan.last_run)}, more than {days} days ago. "
                    f"Fetching only the last {days} days: {dates}."
                )
            case _:
                return (
                    f"The last run was on {self._day(plan.last_run)}. Fetching {dates}, "
                    "from the day before it, to catch postings listed late."
                )

    def _each(self, plan: WindowPlan) -> str:
        """One source's dates, and why those, when the sources' dates differ."""
        dates = self._dates(plan.window)
        days = (plan.window.end - plan.window.start).days
        last = self._day(plan.last_run)
        match plan.reason:
            case WindowReason.FIRST_RUN:
                return f"{dates}, the last {days} days (not covered by any earlier run)."
            case WindowReason.CAPPED:
                return (
                    f"{dates}, only the last {days} days "
                    f"(last covered on {last}, more than {days} days ago)."
                )
            case WindowReason.CATCHING_UP:
                return (
                    f"{dates}, catching up (not covered in the last run; last covered on {last})."
                )
            case _:
                return f"{dates}, from the day before the last run on {last}."

    def _dates(self, window: Window) -> str:
        """A window as the user reads it, e.g. "Nov 2 to Nov 5"."""
        return f"{self._day(window.start)} to {self._day(window.end)}"

    def _day(self, day: date | None) -> str:
        """A date as the user reads it, e.g. "Nov 5"."""
        return f"{day:%b} {day.day}" if day else "an unknown date"
