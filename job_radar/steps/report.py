"""Step 6: write the report."""

from job_radar.checkpoints import RunStats
from job_radar.model import Recommendation, Report
from job_radar.report_writer import ReportWriter


class ReportStep:
    """Builds the run's report: the funnel of counts and the recommended jobs.

    Stateless: holds only where it reads counts from and where the report goes.
    """

    name = "report"
    output = Report

    def __init__(self, stats: RunStats, writer: ReportWriter) -> None:
        """Keep the run's counts and the writer the report goes to."""
        self._stats = stats
        self._writer = writer

    def run(self, data: list[Recommendation]) -> list[Report]:
        """Build the Markdown report, write it, and say where it is."""
        # TODO(task 8): build the funnel and the top N in Markdown.
        raise NotImplementedError
