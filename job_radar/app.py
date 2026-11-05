"""The app: lives for one terminal command and runs it."""

from job_radar.pipeline import Pipeline
from job_radar.result import RunResult


class JobRadarApp:
    """Runs one terminal command and hands back how it ended.

    Lives only while that command runs. Stateless: holds only its pipeline,
    which it launches as a black box.
    """

    def __init__(self, pipeline: Pipeline) -> None:
        """Keep the pipeline this app launches."""
        self._pipeline = pipeline

    def run(self) -> RunResult:
        """Launch the pipeline and return how the run ended."""
        return self._pipeline.run()
