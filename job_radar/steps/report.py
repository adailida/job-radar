"""Step 12: write the report."""

from collections.abc import Mapping

from job_radar.asks import AskSource
from job_radar.checkpoints import RunStats
from job_radar.cost import SpendLog
from job_radar.gaps import GapSource
from job_radar.model import (
    Job,
    Recommendation,
    Report,
    ReportContent,
    SourceSummary,
    Spend,
    SpendDecision,
    Window,
)
from job_radar.openings import OpeningGrouper
from job_radar.report_renderer import ReportRenderer
from job_radar.report_writer import ReportWriter
from job_radar.source_counts import SourceCountLog
from job_radar.trends import KeptJobs, TrendSource
from job_radar.usage import PendingLog


class ReportStep:
    """Puts together what the run's report says, then has it formatted and written.

    The content is the run's window and sources, any days a long break left
    out, the alerts, the recommended jobs, every new matched job by group, the
    market trends, what employers ask for and how the CV compares with it, the
    funnel of counts, what paid sources spent and how many jobs are carried
    over to the next run; the renderer decides only how it looks. Its summary
    for the terminal counts the new openings, the recommended jobs and the
    alerts. Stateless: holds only where it reads each part from, the
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
        sources: Mapping[str, str],
        counts: SourceCountLog,
        this_run: KeptJobs,
        grouper: OpeningGrouper,
    ) -> None:
        """Keep where each part of the report comes from, how it is written, and the run's facts.

        `sources` names the run's sources for people, by their name in the
        data, in the order they were fetched. `this_run` gives the run's
        matched jobs, the new openings.
        """
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
        self._sources = sources
        self._counts = counts
        self._this_run = this_run
        self._grouper = grouper

    def run(self, data: list[Recommendation]) -> list[Report]:
        """Build the report's content, write it, and say where it is and what it found."""
        asks = self._asks.asks()
        spends = self._spend.spends()
        scores = {rec.job.id: rec.score for rec in data}
        content = ReportContent(
            run=self._run_id,
            window=self._window,
            not_covered=self._not_covered,
            sources=self._summaries(spends),
            # TODO(task 24): the run's warnings as alerts; none until then.
            min_score=self._min_score,
            recommendations=tuple(data),
            openings=self._grouper.group(self._this_run.kept(Job), scores),
            funnel=tuple(self._stats.funnel()),
            spends=tuple(spends),
            carried_over=len(self._pending.jobs()),
            trends=self._trends.trends(),
            asks=asks,
            gaps=self._gaps.gaps(asks) if asks is not None else None,
        )
        location = self._writer.write(self._renderer.render(content))
        return [Report(location=location, summary=self._summary(content))]

    def _summaries(self, spends: list[Spend]) -> tuple[SourceSummary, ...]:
        """Each of the run's sources: its name, the postings it gave, and what a paid one cost."""
        given = {count.source: count.postings for count in self._counts.counts()}
        paid = {spend.approval.source: spend for spend in spends}
        summaries = []
        for source, name in self._sources.items():
            spend = paid.get(source)
            skipped = spend is not None and spend.approval.decision is SpendDecision.SKIPPED
            summaries.append(
                SourceSummary(
                    source=source,
                    name=name,
                    postings=given.get(source, 0),
                    credits=spend.charged if spend is not None and not skipped else None,
                    skipped=skipped,
                )
            )
        return tuple(summaries)

    @staticmethod
    def _summary(content: ReportContent) -> str:
        """The run in one line: "23 new openings, 10 recommended, 0 alerts"."""
        openings = content.new_openings
        alerts = len(content.alerts)
        return (
            f"{openings} new opening{'' if openings == 1 else 's'}, "
            f"{len(content.recommendations)} recommended, "
            f"{alerts} alert{'' if alerts == 1 else 's'}"
        )
