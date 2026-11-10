"""Step 12: write the report."""

from job_radar.asks import AskSource
from job_radar.checkpoints import RunStats
from job_radar.cost import SpendLog
from job_radar.gaps import GapSource
from job_radar.model import Recommendation, Report, ReportContent, Window
from job_radar.report_renderer import ReportRenderer
from job_radar.report_writer import ReportWriter
from job_radar.trends import TrendSource
from job_radar.usage import PendingLog


class ReportStep:
    """Puts together what the run's report says, then has it formatted and written.

    The content is the recommended jobs, the run's window, any days a long
    break left out, the market trends, what employers ask for and how the CV
    compares with it, the funnel of counts, what paid sources spent and how
    many jobs are carried over to the next run; the renderer decides only how
    it looks. Stateless: holds only where it reads counts, trends,
    requirements, the CV comparison, spend and carried-over jobs from, the
    renderer, where the report goes, and what it needs to know about the run.
    """

    name = "report"
    output = Report

    def __init__(
        self,
        stats: RunStats,
        renderer: ReportRenderer,
        writer: ReportWriter,
        spend: SpendLog,
        pending: PendingLog,
        trends: TrendSource,
        asks: AskSource,
        gaps: GapSource,
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
        self._pending = pending
        self._trends = trends
        self._asks = asks
        self._gaps = gaps
        self._run_id = run_id
        self._window = window
        self._not_covered = not_covered
        self._min_score = min_score

    def run(self, data: list[Recommendation]) -> list[Report]:
        """Build the report's content, write it, and say where it is."""
        asks = self._asks.asks()
        content = ReportContent(
            run=self._run_id,
            window=self._window,
            not_covered=self._not_covered,
            min_score=self._min_score,
            recommendations=tuple(data),
            funnel=tuple(self._stats.funnel()),
            spends=tuple(self._spend.spends()),
            carried_over=len(self._pending.jobs()),
            trends=self._trends.trends(),
            asks=asks,
            gaps=self._gaps.gaps(asks) if asks is not None else None,
        )
        location = self._writer.write(self._renderer.render(content))
        jobs = "job" if len(data) == 1 else "jobs"
        return [Report(location=location, summary=f"{len(data)} {jobs} recommended")]
