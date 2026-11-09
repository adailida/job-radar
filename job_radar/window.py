"""Which dates a run fetches postings for."""

from datetime import date, timedelta
from enum import StrEnum

from job_radar.model import Model, Window


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
