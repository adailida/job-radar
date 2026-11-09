"""Step 10: write the report."""

from job_radar.checkpoints import RunStats
from job_radar.cost import SpendLog
from job_radar.model import Recommendation, Report, ReportContent, Window
from job_radar.report_renderer import ReportRenderer
from job_radar.report_writer import ReportWriter


class ReportStep:
    """Puts together what the run's report says, then has it formatted and written.

    The content is the recommended jobs, the run's window, any days a long
    break left out, the funnel of counts and what paid sources spent; the
    renderer decides only how it looks. Stateless: holds only where it reads
    counts and spend from, the renderer, where the report goes, and what it
    needs to know about the run.
    """

    name = "report"
    output = Report

    def __init__(
        self,
        stats: RunStats,
        renderer: ReportRenderer,
        writer: ReportWriter,
        spend: SpendLog,
        run_id: str,
        window: Window,
        not_covered: Window | None,
        min_score: int,
    ) -> None:
        """Keep the run's counts, how the report is formatted and stored, and the run's facts."""
        self._stats = stats
        self._renderer = renderer
        self._writer = writer
        self._spend = spend
        self._run_id = run_id
        self._window = window
        self._not_covered = not_covered
        self._min_score = min_score

    def run(self, data: list[Recommendation]) -> list[Report]:
        """Build the report's content, write it, and say where it is."""
        content = ReportContent(
            run=self._run_id,
            window=self._window,
            not_covered=self._not_covered,
            min_score=self._min_score,
            recommendations=tuple(data),
            funnel=tuple(self._stats.funnel()),
            spends=tuple(self._spend.spends()),
        )
        location = self._writer.write(self._renderer.render(content))
        jobs = "job" if len(data) == 1 else "jobs"
        return [Report(location=location, summary=f"{len(data)} {jobs} recommended")]
