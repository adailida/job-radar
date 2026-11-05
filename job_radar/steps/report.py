"""Step 6: write the report."""

from job_radar.checkpoints import RunStats
from job_radar.model import Recommendation, Report, Window
from job_radar.report_writer import ReportWriter


class ReportStep:
    """Builds the run's report: the funnel of counts and the recommended jobs.

    Stateless: holds only where it reads counts from, where the report goes,
    and the run's window.
    """

    name = "report"
    output = Report

    def __init__(self, stats: RunStats, writer: ReportWriter, window: Window) -> None:
        """Keep the run's counts, the writer the report goes to, and the run's window."""
        self._stats = stats
        self._writer = writer
        self._window = window

    def run(self, data: list[Recommendation]) -> list[Report]:
        """Build the Markdown report, write it, and say where it is."""
        # TODO(task 8): add work mode and salary; settle the layout with a golden file.
        lines = ["# job-radar report", "", f"## Recommended jobs ({len(data)})", ""]
        if not data:
            lines.append("No jobs to recommend this run.")
        for rank, rec in enumerate(data, start=1):
            lines.extend(self._job(rank, rec))
        window = f"{self._window.start.isoformat()} to {self._window.end.isoformat()}"
        lines.extend(["", "## About this run", "", f"Postings from {window}.", ""])
        lines.extend(["Items each step produced:", ""])
        lines.extend(f"- {count.step}: {count.count}" for count in self._stats.funnel())
        location = self._writer.write("\n".join(lines) + "\n")
        jobs = "job" if len(data) == 1 else "jobs"
        return [Report(location=location, summary=f"{len(data)} {jobs} recommended")]

    def _job(self, rank: int, rec: Recommendation) -> list[str]:
        """One recommended job as a numbered list item, from its primary posting."""
        posting = rec.job.postings[0]
        places = ", ".join(location.text for location in posting.locations)
        return [
            f"{rank}. **{posting.title}**, {posting.company} (score {rec.score})",
            f"   {places}. {posting.url}",
            f"   {rec.reason}",
        ]
