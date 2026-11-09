"""Turning a report's content into text."""

from datetime import timedelta
from typing import Protocol, runtime_checkable

from job_radar.model import Recommendation, ReportContent, Spend, SpendDecision
from job_radar.words import Words


@runtime_checkable
class ReportRenderer(Protocol):
    """Formats a report's content as text, deciding nothing about what it says. Stateless."""

    def render(self, content: ReportContent) -> str:
        """The whole report as text."""
        ...


class MarkdownRenderer:
    """Formats a report as Markdown, with YAML front matter for tools and LLMs.

    Plain text only: words instead of symbols, "to" for ranges, no HTML.
    Stateless: holds only how facts and dates are put into words.
    """

    def __init__(self, words: Words) -> None:
        """Keep how facts and dates are put into words."""
        self._words = words

    def render(self, content: ReportContent) -> str:
        """The report: front matter, title, recommended jobs, then the funnel."""
        recs = content.recommendations
        window = content.window
        lines = [
            "---",
            f"run: {content.run}",
            f"covers: [{window.start.isoformat()}, {window.end.isoformat()}]",
            *self._gap_matter(content),
            f"recommended: {len(recs)}",
            "---",
            "",
            f"# job-radar report, {self._words.day(window.end, year=True)}",
            "",
            f"Covers postings from {self._words.span(window.start, window.end)}.",
            *self._gap_note(content),
            "",
            f"## Recommended jobs ({len(recs)})",
            "",
        ]
        if not recs:
            lines.append(f"No job scored {content.min_score} or more this run.")
        for rank, rec in enumerate(recs, start=1):
            lines.extend(self._job(rank, rec))
        lines.extend(["", "## About this run", "", "Items each step produced:", ""])
        lines.extend(f"- {count.step}: {count.count}" for count in content.funnel)
        if content.spends:
            lines.extend(["", "Paid sources:", ""])
            lines.extend(f"- {self._spend(spend)}" for spend in content.spends)
        lines.extend(["", "Jobs the filter dropped, by reason: dropped.md"])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _gap_matter(content: ReportContent) -> list[str]:
        """The front matter line for days a long break left out, if any."""
        gap = content.not_covered
        return [f"not_covered: [{gap.start.isoformat()}, {gap.end.isoformat()}]"] if gap else []

    def _gap_note(self, content: ReportContent) -> list[str]:
        """Say which days a long break left out, and why, if any."""
        gap = content.not_covered
        if gap is None:
            return []
        days = (content.window.end - content.window.start).days
        last = self._words.day(gap.start - timedelta(days=1))
        return [
            "",
            f"Not covered: {self._words.span(gap.start, gap.end)}. The last run was on {last}, "
            f"and a run reaches back at most {days} days.",
        ]

    @staticmethod
    def _spend(spend: Spend) -> str:
        """One paid source's spend in words: the estimate, how it was agreed, what it cost."""
        approval = spend.approval
        agreed = {
            SpendDecision.AUTO: "within every limit",
            SpendDecision.APPROVED: "over a limit, approved by you",
            SpendDecision.SKIPPED: "skipped by you",
        }[approval.decision]
        said = f"{approval.source}: estimate {approval.estimate} credits, {agreed}"
        if approval.decision is SpendDecision.SKIPPED:
            return said + f". {approval.credits_before} credits left."
        return said + f". {spend.charged} used, {spend.credits_after} left."

    def _job(self, rank: int, rec: Recommendation) -> list[str]:
        """One job as a numbered list item: its primary posting, the reason, a link per posting."""
        posting = rec.job.postings[0]
        links = ", ".join(f"[{p.source}]({p.url})" for p in rec.job.postings)
        details = self._words.details(posting)
        return [
            f"{rank}. **{posting.title}**, {posting.company} (score {rec.score})",
            *([f"   {details}"] if details else []),
            f"   {rec.reason}",
            f"   {links}",
        ]
