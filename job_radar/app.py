"""The app: lives for one terminal command and runs it."""

from collections.abc import Callable

from job_radar.model import Window
from job_radar.pipeline import Pipeline
from job_radar.result import RunCancelled, RunResult
from job_radar.resume import ResumeOffer
from job_radar.window_chooser import WindowChooser


class JobRadarApp:
    """Runs one terminal command and hands back how it ended.

    Offers first to resume the last run if it failed; otherwise agrees a new
    run's window with the user. Then has the pipeline built for that run and
    launches it as a black box. Lives only while that command runs. Stateless:
    holds only the resume offer, the window chooser and how to build the
    pipeline.
    """

    def __init__(
        self,
        offer: ResumeOffer,
        chooser: WindowChooser,
        build: Callable[[Window, str | None], Pipeline],
    ) -> None:
        """Keep who offers a resume, who agrees the window, and how to build the pipeline.

        `build` takes the window and the run to resume, or None for a new run.
        """
        self._offer = offer
        self._chooser = chooser
        self._build = build

    def run(self) -> RunResult:
        """Resume the failed run or agree a new window, run the pipeline, say how it ended."""
        failed = self._offer.offer()
        if failed is not None:
            return self._build(failed.window, failed.id).run()
        window = self._chooser.choose()
        if window is None:
            return RunCancelled()
        return self._build(window, None).run()
