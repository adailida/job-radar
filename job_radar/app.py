"""The app: lives for one terminal command and runs it."""

from collections.abc import Callable

from job_radar.cost import CostCheck
from job_radar.model import Approval, Window
from job_radar.pipeline import Pipeline
from job_radar.result import RunCancelled, RunResult
from job_radar.resume import ResumeOffer
from job_radar.run_lock import RunLock
from job_radar.window_chooser import WindowChooser


class JobRadarApp:
    """Runs one terminal command and hands back how it ended.

    Takes the run lock first, so only one run goes at a time, and releases
    it however the run ends. Offers to resume the last run if it failed;
    otherwise agrees a new run's window with the user. Then agrees what paid
    sources may spend, and only then has the pipeline built for that run and
    launches it as a black box, so stopping at the cost check leaves no run
    behind. Lives only while that command runs. Stateless: holds only the
    resume offer, the window chooser, the cost check, how to build the
    pipeline and the lock.
    """

    def __init__(
        self,
        offer: ResumeOffer,
        chooser: WindowChooser,
        cost: CostCheck,
        build: Callable[[Window, Window | None, str | None, list[Approval]], Pipeline],
        lock: RunLock,
    ) -> None:
        """Keep who offers a resume, who agrees the window and the spend, how to build, the lock.

        `build` takes the window, the days a long break left out (or None),
        the run to resume (or None for a new run), and the spend approvals.
        """
        self._offer = offer
        self._chooser = chooser
        self._cost = cost
        self._build = build
        self._lock = lock

    def run(self) -> RunResult:
        """Take the lock, then resume or start a run and say how it ended.

        Raises `RunInProgress` when another run holds the lock.
        """
        with self._lock:
            return self._run()

    def _run(self) -> RunResult:
        """Resume the failed run or agree a new window, run the pipeline, say how it ended."""
        failed = self._offer.offer()
        if failed is not None:
            window, gap, run_id = failed.window, failed.not_covered, failed.id
        else:
            plan = self._chooser.choose()
            if plan is None:
                return RunCancelled()
            window, gap, run_id = plan.window, plan.not_covered(), None
        approvals = self._cost.check(window)
        if approvals is None:
            return RunCancelled()
        return self._build(window, gap, run_id, approvals).run()
