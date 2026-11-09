"""Turning a report's content into text."""

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from job_radar.model import Period, Posting, Recommendation, ReportContent, Salary, WorkMode


@runtime_checkable
class ReportRenderer(Protocol):
    """Formats a report's content as text, deciding nothing about what it says. Stateless."""

    def render(self, content: ReportContent) -> str:
        """The whole report as text."""
        ...


class MarkdownRenderer:
    """Formats a report as Markdown, with YAML front matter for tools and LLMs.

    Plain text only: words instead of symbols, "to" for ranges, no HTML.
    Stateless.
    """

    WORK_MODES = {WorkMode.REMOTE: "Remote", WorkMode.HYBRID: "Hybrid", WorkMode.ONSITE: "On-site"}
    PERIODS = {Period.YEAR: "a year", Period.MONTH: "a month", Period.HOUR: "an hour"}

    def render(self, content: ReportContent) -> str:
        """The report: front matter, title, recommended jobs, then the funnel."""
        recs = content.recommendations
        window = content.window
        lines = [
            "---",
            f"run: {content.run}",
            f"covers: [{window.start.isoformat()}, {window.end.isoformat()}]",
            f"recommended: {len(recs)}",
            "---",
            "",
            f"# job-radar report, {self._day(window.end, year=True)}",
            "",
            f"Covers postings from {self._range(window.start, window.end)}.",
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
        return "\n".join(lines) + "\n"

    def _job(self, rank: int, rec: Recommendation) -> list[str]:
        """One job as a numbered list item: its primary posting, the reason, a link per posting."""
        posting = rec.job.postings[0]
        links = ", ".join(f"[{p.source}]({p.url})" for p in rec.job.postings)
        details = self._details(posting)
        return [
            f"{rank}. **{posting.title}**, {posting.company} (score {rec.score})",
            *([f"   {details}"] if details else []),
            f"   {rec.reason}",
            f"   {links}",
        ]

    def _details(self, posting: Posting) -> str:
        """Work mode, places, salary and posted date, each left out when unknown."""
        parts = [
            self.WORK_MODES.get(posting.work_mode, ""),
            "; ".join(location.text for location in posting.locations),
            self._salary(posting.salary) if posting.salary else "",
            f"Posted {self._day(posting.posted_at)}" if posting.posted_at else "",
        ]
        return " ".join(f"{part}." for part in parts if part)

    def _salary(self, salary: Salary) -> str:
        """A pay range in words: "$150k to $180k a year", "From EUR 50k a year"."""
        low, high = salary.min, salary.max
        period = self.PERIODS[salary.period]
        if low is not None and high is not None and low != high:
            pay = f"{self._money(low, salary.currency)} to {self._money(high, salary.currency)}"
        elif low is not None and high is None:
            pay = f"From {self._money(low, salary.currency)}"
        elif low is None and high is not None:
            pay = f"Up to {self._money(high, salary.currency)}"
        else:
            pay = self._money(low or high or Decimal(0), salary.currency)
        return f"{pay} {period}"

    @staticmethod
    def _money(amount: Decimal, currency: str) -> str:
        """An amount with its currency, thousands as "k": "$150k", "EUR 52.5k", "$45.50"."""
        if amount >= 1000:
            number = f"{(amount / 1000).normalize():f}k"
        elif amount == amount.to_integral_value():
            number = f"{amount:.0f}"
        else:
            number = f"{amount:.2f}"
        return f"${number}" if currency == "USD" else f"{currency} {number}"

    @staticmethod
    def _day(day: date, year: bool = False) -> str:
        """A day in words: "8 Nov", or "8 Nov 2026" with the year."""
        return f"{day.day} {day:%b}" + (f" {day.year}" if year else "")

    def _range(self, start: date, end: date) -> str:
        """Two days as a range, the year said once when they share it."""
        if start == end:
            return self._day(end, year=True)
        if start.year == end.year:
            return f"{self._day(start)} to {self._day(end, year=True)}"
        return f"{self._day(start, year=True)} to {self._day(end, year=True)}"
