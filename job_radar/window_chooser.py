"""Agreeing a run's window with the user before anything is fetched."""

from datetime import date

from job_radar.clock import Clock
from job_radar.history import RunHistory
from job_radar.model import Window
from job_radar.prompter import Prompter
from job_radar.window import WindowPlan, WindowPlanner, WindowReason


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

    def choose(self) -> Window | None:
        """The window to fetch, or None if the user said no."""
        plan = self._planner.plan(self._clock.now().date(), self._history.last_window())
        self._prompter.tell(self._describe(plan))
        if plan.reason is WindowReason.SINCE_LAST_RUN or self._prompter.confirm("Continue?"):
            return plan.window
        return None

    def _describe(self, plan: WindowPlan) -> str:
        """Say which dates the run will fetch, and why those."""
        dates = f"{self._day(plan.window.start)} to {self._day(plan.window.end)}"
        days = (plan.window.end - plan.window.start).days
        match plan.reason:
            case WindowReason.FIRST_RUN:
                return f"No earlier runs. Fetching the last {days} days: {dates}."
            case WindowReason.CAPPED:
                # TODO(task 14): the report notes the dates the gap left out.
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
