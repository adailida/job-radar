"""Which dates a run fetches postings for, agreed with the user before anything is fetched."""

from datetime import date, timedelta
from enum import StrEnum

from job_radar.models import Model, Window
from job_radar.storage.run_history import RunHistory
from job_radar.utils.clock import Clock
from job_radar.utils.prompter import Prompter


class WindowReason(StrEnum):
    """Why a run's window starts where it does."""

    FIRST_RUN = "first_run"  # no completed run yet: the whole lookback
    SINCE_LAST_RUN = "since_last_run"  # picks up where the last completed run ended
    CAPPED = "capped"  # the last run is older than the lookback: the lookback only


class WindowPlan(Model):
    """A run's window, why it was chosen, and when the last completed run ended."""

    window: Window
    reason: WindowReason
    last_run: date | None = None

    def not_covered(self) -> Window | None:
        """The days between the last run and this window, when the lookback cut them off."""
        if self.reason is not WindowReason.CAPPED or self.last_run is None:
            return None
        start, end = self.last_run + timedelta(days=1), self.window.start - timedelta(days=1)
        return Window(start=start, end=end) if start <= end else None


class WindowPlanner:
    """Decides the dates a run covers, from the last completed run and the lookback.

    A run starts one day before the last run's last day. That day is fetched
    again because the last run may have been early in it, and the day before
    because boards can list a posting a day after its date. Repeats are cheap,
    and recognising jobs already seen removes them. Stateless: holds only the
    lookback.
    """

    MARGIN = timedelta(days=1)

    def __init__(self, lookback_days: int) -> None:
        """Keep how many days back a run may reach at most."""
        self._lookback = timedelta(days=lookback_days)

    def plan(self, today: date, last: Window | None) -> WindowPlan:
        """The window for a run today, given the last completed run's window, if any."""
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
        return WindowPlan(
            window=Window(start=start, end=today),
            reason=WindowReason.SINCE_LAST_RUN,
            last_run=last.end,
        )


class WindowChooser:
    """Works out the run's window and agrees it with the user.

    After a recent run it says which dates it will fetch and goes ahead. On a
    first run, or when the last run is older than the lookback, it asks first,
    since the run reaches back further than usual. Stateless: holds only what
    it reads from and who it asks.
    """

    def __init__(
        self, history: RunHistory, planner: WindowPlanner, prompter: Prompter, clock: Clock
    ) -> None:
        """Keep where earlier runs are read from, the planner, the user, and the clock."""
        self._history = history
        self._planner = planner
        self._prompter = prompter
        self._clock = clock

    def choose(self) -> WindowPlan | None:
        """The plan for the run's window, or None if the user said no."""
        plan = self._planner.plan(self._clock.now().date(), self._history.last_window())
        self._prompter.tell(self._describe(plan))
        if plan.reason is WindowReason.SINCE_LAST_RUN or self._prompter.confirm("Continue?"):
            return plan
        return None

    def _describe(self, plan: WindowPlan) -> str:
        """Say which dates the run will fetch, and why those."""
        dates = f"{self._day(plan.window.start)} to {self._day(plan.window.end)}"
        days = (plan.window.end - plan.window.start).days
        match plan.reason:
            case WindowReason.FIRST_RUN:
                return f"No earlier runs. Fetching the last {days} days: {dates}."
            case WindowReason.CAPPED:
                return (
                    f"The last run was on {self._day(plan.last_run)}, more than {days} days ago. "
                    f"Fetching only the last {days} days: {dates}."
                )
            case WindowReason.SINCE_LAST_RUN:
                return (
                    f"The last run was on {self._day(plan.last_run)}. Fetching {dates}, "
                    "from the day before it, to catch postings listed late."
                )

    def _day(self, day: date | None) -> str:
        """A date as the user reads it, e.g. "Nov 5"."""
        return f"{day:%b} {day.day}" if day else "an unknown date"
