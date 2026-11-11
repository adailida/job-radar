"""The app: lives for one terminal command and runs it."""

from collections.abc import Callable

from job_radar.app.cost_check import CostCheck
from job_radar.app.resume_offer import ResumeOffer
from job_radar.app.run_result import RunCancelled, RunResult
from job_radar.app.window import WindowChooser
from job_radar.models import Approval, RunWindows
from job_radar.pipeline.pipeline import Pipeline
from job_radar.storage.run_lock import RunLock


class JobRadarApp:
    """Runs one terminal command and hands back how it ended.

    Takes the run lock first, so only one run goes at a time, and releases
    it however the run ends. Offers to resume the last run if it failed;
    otherwise agrees a new run's windows with the user. Then agrees what paid
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
        build: Callable[[RunWindows, str | None, list[Approval]], Pipeline],
        lock: RunLock,
    ) -> None:
        """Keep who offers a resume, who agrees the windows and the spend, how to build, the lock.

        `build` takes the run's windows (each source's own and the one that
        spans them), the run to resume (or None for a new run), and the spend
        approvals.
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
        """Resume the failed run or agree new windows, run the pipeline, say how it ended."""
        failed = self._offer.offer()
        if failed is not None:
            windows, run_id = failed.windows(), failed.id
        else:
            chosen = self._chooser.choose()
            if chosen is None:
                return RunCancelled()
            windows, run_id = chosen, None
        approvals = self._cost.check(windows)
        if approvals is None:
            return RunCancelled()
        return self._build(windows, run_id, approvals).run()
