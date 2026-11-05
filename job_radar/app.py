"""The app: lives for one terminal command and runs it."""

from collections.abc import Callable

from job_radar.model import Window
from job_radar.pipeline import Pipeline
from job_radar.result import RunCancelled, RunResult
from job_radar.window_chooser import WindowChooser


class JobRadarApp:
    """Runs one terminal command and hands back how it ended.

    Agrees the run's window with the user first, then has the pipeline built
    for that window and launches it as a black box. Lives only while that
    command runs. Stateless: holds only the window chooser and how to build the
    pipeline.
    """

    def __init__(self, chooser: WindowChooser, build: Callable[[Window], Pipeline]) -> None:
        """Keep who agrees the window, and how to build the pipeline for a window."""
        self._chooser = chooser
        self._build = build

    def run(self) -> RunResult:
        """Agree the window, then run the pipeline and return how the run ended."""
        window = self._chooser.choose()
        if window is None:
            return RunCancelled()
        return self._build(window).run()
