"""Turning a report's content into text."""

from datetime import timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable

from job_radar.model import (
    AskRow,
    Asks,
    Gaps,
    GapSkip,
    GapStatus,
    Job,
    Opening,
    OpeningGroup,
    Recommendation,
    ReportContent,
    RequirementType,
    Seniority,
    SourceSummary,
    Spend,
    SpendDecision,
    TrendPeriod,
    Trends,
)
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

    ASK_HEADINGS = {
        RequirementType.SKILL: "Skills",
        RequirementType.TOOL: "Tools",
        RequirementType.CERTIFICATION: "Certifications",
        RequirementType.YEARS: "Years of experience",
    }

    def __init__(self, words: Words) -> None:
        """Keep how facts and dates are put into words."""
        self._words = words

    def render(self, content: ReportContent) -> str:
        """The report: front matter, the header, then every section, always in the same order.

        Alerts, recommended jobs, new openings, market trends, what employers
        ask for, experience to gain, and about this run.
        """
        recs = content.recommendations
        window = content.window
        names = {source.source: source.name for source in content.sources}
        counts = ", ".join(f"{source.source}: {source.postings}" for source in content.sources)
        lines = [
            "---",
            f"run: {content.run}",
            f"covers: [{window.start.isoformat()}, {window.end.isoformat()}]",
            *self._gap_matter(content),
            f"sources: {{{counts}}}",
            f"new_openings: {content.new_openings}",
            f"recommended: {len(recs)}",
            f"alerts: {len(content.alerts)}",
            "---",
            "",
            f"# job-radar report, {self._words.day(window.end, year=True)}",
            "",
            f"Covers postings from {self._words.span(window.start, window.end)}.",
            *self._gap_note(content),
            "",
            self._sources(content.sources),
            "",
            "## Alerts",
            "",
            *([f"- {alert.message}" for alert in content.alerts] or ["None."]),
            "",
            f"## Recommended jobs ({len(recs)})",
            "",
        ]
        if not recs:
            lines.append(f"No job scored {content.min_score} or more this run.")
        for rank, rec in enumerate(recs, start=1):
            lines.extend(self._job(rank, rec, names))
        lines.extend(["", *self._openings(content, names)])
        lines.extend(["", *self._trends(content.trends)])
        lines.extend(["", *self._asks(content.asks)])
        lines.extend(["", *self._gaps(content.gaps)])
        lines.extend(["", "## About this run", "", "Items each step produced:", ""])
        lines.extend(f"- {count.step}: {count.count}" for count in content.funnel)
        if content.spends:
            lines.extend(["", "Paid sources:", ""])
            lines.extend(f"- {self._spend(spend, names)}" for spend in content.spends)
        if content.carried_over:
            jobs = "job" if content.carried_over == 1 else "jobs"
            lines.extend(
                ["", f"{content.carried_over} {jobs} carried over to the next run (usage limit)."]
            )
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
    def _sources(sources: tuple[SourceSummary, ...]) -> str:
        """The sources line: each source's name, its postings, and the credits a paid one used."""
        said = []
        for source in sources:
            if source.skipped:
                said.append(f"{source.name} skipped by you")
                continue
            plural = "" if source.postings == 1 else "s"
            text = f"{source.name} {source.postings:,} posting{plural}"
            if source.credits is not None:
                text += f" ({source.credits:,} credit{'' if source.credits == 1 else 's'})"
            said.append(text)
        return f"Sources: {', '.join(said) or 'none'}."

    def _openings(self, content: ReportContent, names: dict[str, str]) -> list[str]:
        """The new openings section: every new matched job, one line each, under its group."""
        lines = [f"## New openings ({content.new_openings})"]
        if not content.openings:
            return [*lines, "", "No new job matched your searches this run."]
        for group in content.openings:
            lines.extend(self._group(group, 3, names))
        return lines

    def _group(self, group: OpeningGroup, level: int, names: dict[str, str]) -> list[str]:
        """One group's heading at this level, then its jobs or the groups inside it."""
        lines = ["", f"{'#' * level} {group.name} ({group.size})"]
        if group.openings:
            lines.append("")
            lines.extend(self._opening(opening, names) for opening in group.openings)
        for inside in group.groups:
            lines.extend(self._group(inside, level + 1, names))
        return lines

    def _opening(self, opening: Opening, names: dict[str, str]) -> str:
        """One new opening as a list item: title, company, details, its score if any, links."""
        posting = opening.job.postings[0]
        details = self._words.details(posting)
        parts = [
            f"**{posting.title}**, {posting.company}.",
            *([details] if details else []),
            *([f"Recommended, score {opening.score}."] if opening.score is not None else []),
            self._links(opening.job, names),
        ]
        return "- " + " ".join(parts)

    @staticmethod
    def _links(job: Job, names: dict[str, str]) -> str:
        """A link to each of a job's postings, labelled with its source's name for people."""
        return ", ".join(f"[{names.get(p.source, p.source)}]({p.url})" for p in job.postings)

    def _trends(self, trends: Trends | None) -> list[str]:
        """The market trends section: notes, then a table of periods, then the change."""
        if trends is None:
            return ["## Market trends", "", "No runs to show trends for yet."]
        lines = [f"## Market trends (by {trends.period})", ""]
        periods = list(trends.periods)
        if not periods:
            return [*lines, "No runs to show trends for yet."]
        for note in trends.notes:
            lines.append(f"Note: {self._words.day(note.day)}: {'; '.join(note.changes)}.")
        if trends.notes:
            lines.append("")
        change = trends.change
        years = len({p.start.year for p in periods}) > 1
        header = ["", *(self._period_label(trends.period, p, years) for p in periods)]
        if change:
            header.append("Change")
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        low = trends.low_sample
        rows: list[tuple[str, list[str], str]] = []
        rows.append(
            (
                "New postings per covered day",
                [self._sample(self._decimal(p.per_day), p.postings, low) for p in periods],
                self._percent(change.per_day) if change else "",
            )
        )
        rows.append(("Postings", [str(p.postings) for p in periods], ""))
        for mode, label in (("remote", "Remote"), ("hybrid", "Hybrid"), ("onsite", "On-site")):
            if any(mode in p.work_modes for p in periods):
                cells = [
                    self._sample(self._share(p.work_modes.get(mode, 0.0)), p.work_mode_base, low)
                    if p.work_mode_base
                    else "no data"
                    for p in periods
                ]
                rows.append(
                    (label, cells, self._points(change.work_modes.get(mode)) if change else "")
                )
        rows.append(("Work mode not given (jobs)", [str(p.work_mode_unknown) for p in periods], ""))
        rows.append(
            (
                "Salary median, USD a year",
                [self._sample(self._usd(p.salary_median), p.salary_base, low) for p in periods],
                self._percent(change.salary_median) if change else "",
            )
        )
        rows.append(
            (
                "Salary, 25th to 75th percentile",
                [
                    f"{self._usd(p.salary_p25)} to {self._usd(p.salary_p75)}"
                    if p.salary_base
                    else "no data"
                    for p in periods
                ],
                "",
            )
        )
        rows.append(
            (
                "Listing a salary",
                [
                    self._share(p.salary_listed) if p.salary_listed is not None else "no data"
                    for p in periods
                ],
                "",
            )
        )
        for level in (s.value for s in Seniority):
            if any(level in p.seniority for p in periods):
                cells = [
                    self._sample(self._share(p.seniority.get(level, 0.0)), p.seniority_base, low)
                    if p.seniority_base
                    else "no data"
                    for p in periods
                ]
                rows.append(
                    (
                        f"Seniority: {level}",
                        cells,
                        self._points(change.seniority.get(level)) if change else "",
                    )
                )
        rows.append(("Seniority not known (jobs)", [str(p.seniority_unknown) for p in periods], ""))
        for label, cells, delta in rows:
            line = [label, *cells, *([delta] if change else [])]
            lines.append("| " + " | ".join(line) + " |")
        lines.append("")
        if change:
            against = self._period_label(
                trends.period, self._period_at(periods, change.against), years
            )
            lines.append(f"Change: the latest {trends.period} against {against}, per covered day.")
        else:
            lines.append(
                f"Nothing to compare yet: the change needs a complete {trends.period} "
                "before the latest."
            )
        lines.append(f"A figure on fewer than {low} jobs is marked as a low sample.")
        return lines

    def _asks(self, asks: Asks | None) -> list[str]:
        """The what employers ask for section: the window, then a table per requirement type."""
        if asks is None:
            return ["## What employers ask for", "", "No matched job with requirements yet."]
        days = (asks.window.end - asks.window.start).days + 1
        span = self._words.span(asks.window.start, asks.window.end)
        lines = ["## What employers ask for", ""]
        if not asks.jobs:
            return [*lines, f"No matched job with requirements in the {days} days from {span}."]
        jobs = "job" if asks.jobs == 1 else "jobs"
        low = " (low sample)" if asks.jobs < asks.low_sample else ""
        lines.append(f"In the {days} days from {span}: {asks.jobs} matched {jobs}{low}.")
        compare = asks.previous_jobs > 0
        for kind, heading in self.ASK_HEADINGS.items():
            rows = [row for row in asks.rows if row.type is kind]
            if not rows:
                continue
            header = ["Requirement", "Share", *(["Change"] if compare else [])]
            lines.extend(["", f"### {heading}", "", "| " + " | ".join(header) + " |"])
            lines.append("|" + "---|" * len(header))
            for row in rows:
                cells = [self._requirement(row), f"{self._share(row.share)} ({row.jobs})"]
                if compare:
                    cells.append(self._points(row.change))
                lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        before = self._words.span(asks.previous.start, asks.previous.end)
        if compare:
            jobs = "job" if asks.previous_jobs == 1 else "jobs"
            lines.append(
                f"Change: in points, against the {days} days from {before} "
                f"({asks.previous_jobs} {jobs})."
            )
        else:
            lines.append(
                f"No change yet: no matched job with requirements in the {days} days before."
            )
        lines.append("Share: of the matched jobs with requirements; failed extractions left out.")
        lines.append(f"Fewer than {asks.low_sample} jobs in the window is a low sample.")
        return lines

    def _gaps(self, gaps: Gaps | None) -> list[str]:
        """The experience to gain section: any note, a table of gaps, then the covered ones."""
        lines = ["## Experience to gain"]
        if gaps is None or (not gaps.rows and gaps.skipped is None):
            return [*lines, "", "No requirements to compare with your CV yet."]
        if gaps.skipped is not None:
            count = gaps.not_compared
            some = f"{count} requirement" if count == 1 else f"{count} requirements"
            why = {
                GapSkip.FAILED: (
                    f"{some} couldn't be compared with your CV this run: "
                    "the LLM gave no usable answer"
                ),
                GapSkip.USAGE_LIMIT: (
                    f"{some} weren't compared with your CV this run: "
                    "the LLM's usage limit is reached"
                ),
            }[gaps.skipped]
            lines.extend(["", f"Note: {why}. They are compared on the next run."])
        if not gaps.rows:
            return lines
        missing = [row for row in gaps.rows if row.status is not GapStatus.COVERED]
        covered = [row for row in gaps.rows if row.status is GapStatus.COVERED]
        lines.append("")
        if missing:
            lines.append("| Requirement | Share | Status | How to gain it |")
            lines.append("|---|---|---|---|")
            for row in missing:
                asked = row.requirement
                cells = [
                    self._cell(self._requirement(asked)),
                    f"{self._share(asked.share)} ({asked.jobs})",
                    self._cell(f"{row.status.value}: {row.reason}"),
                    self._cell(row.suggestion or ""),
                ]
                lines.append("| " + " | ".join(cells) + " |")
        else:
            lines.append("Your CV covers every requirement compared.")
        if covered:
            names = ", ".join(self._requirement(row.requirement) for row in covered)
            lines.extend(["", f"Covered: {names}."])
        lines.append("")
        lines.append(
            "Share: as in What employers ask for. Each requirement is compared with your CV once; "
            "a changed CV is compared again."
        )
        return lines

    def _requirement(self, row: AskRow) -> str:
        """A requirement's name; for years, with the median asked: "engineering: 5 years"."""
        if row.type is RequirementType.YEARS:
            return f"{row.name}: {self._years(row.median_years)}"
        return row.name

    @staticmethod
    def _cell(text: str) -> str:
        """Text safe inside a table cell: a pipe would start a new column."""
        return text.replace("|", "\\|")

    @staticmethod
    def _years(median: float | None) -> str:
        """A median number of years in words: "5 years", "1 year", "years not given"."""
        if median is None:
            return "years not given"
        number = f"{median:g}"
        return f"{number} year" if number == "1" else f"{number} years"

    @staticmethod
    def _period_at(periods: list[TrendPeriod], start) -> TrendPeriod:
        """The shown period that starts on this day."""
        return next(p for p in periods if p.start == start)

    def _period_label(self, kind: str, period: TrendPeriod, years: bool) -> str:
        """A period's name: "Nov", "Nov 2026", "Week of 3 Nov", "Q4 2026", with "partial" if so."""
        if kind == "week":
            name = f"Week of {self._words.day(period.start, year=years)}"
        elif kind == "quarter":
            name = f"Q{(period.start.month - 1) // 3 + 1}" + (
                f" {period.start.year}" if years else ""
            )
        else:
            name = f"{period.start:%b}" + (f" {period.start.year}" if years else "")
        if period.partial:
            name += f" (partial, {period.covered_days} of {period.days} days)"
        return name

    @staticmethod
    def _sample(cell: str, base: int, low: int) -> str:
        """The cell, marked when the figure rests on too few jobs."""
        return f"{cell} (low sample)" if base and base < low else cell

    @staticmethod
    def _decimal(value: float | None) -> str:
        """A number with one decimal, or "no data"."""
        return "no data" if value is None else f"{value:.1f}"

    @staticmethod
    def _share(value: float | None) -> str:
        """A share as a whole percent, or "no data"."""
        return "no data" if value is None else f"{value * 100:.0f}%"

    def _usd(self, amount: int | None) -> str:
        """A yearly USD amount, or "no data"."""
        return "no data" if amount is None else self._words.money(Decimal(amount), "USD")

    @staticmethod
    def _percent(value: float | None) -> str:
        """A percent change in words: "up 16%", "down 4%", "no change", or "no data"."""
        if value is None:
            return "no data"
        if round(value) == 0:
            return "no change"
        return f"{'up' if value > 0 else 'down'} {abs(value):.0f}%"

    @staticmethod
    def _points(value: float | None) -> str:
        """A change in a share, in points: "up 2 pts", "down 3 pts", "no change"."""
        if value is None or round(value) == 0:
            return "no change"
        return f"{'up' if value > 0 else 'down'} {abs(value):.0f} pts"

    @staticmethod
    def _spend(spend: Spend, names: dict[str, str]) -> str:
        """One paid source's spend in words: the estimate, how it was agreed, what it cost."""
        approval = spend.approval
        agreed = {
            SpendDecision.AUTO: "within every limit",
            SpendDecision.APPROVED: "over a limit, approved by you",
            SpendDecision.SKIPPED: "skipped by you",
        }[approval.decision]
        name = names.get(approval.source, approval.source)
        said = f"{name}: estimate {approval.estimate} credits, {agreed}"
        if approval.decision is SpendDecision.SKIPPED:
            return said + f". {approval.credits_before} credits left."
        return said + f". {spend.charged} used, {spend.credits_after} left."

    def _job(self, rank: int, rec: Recommendation, names: dict[str, str]) -> list[str]:
        """One job as a numbered list item: its primary posting, the reason, a link per posting."""
        posting = rec.job.postings[0]
        details = self._words.details(posting)
        return [
            f"{rank}. **{posting.title}**, {posting.company} (score {rec.score})",
            *([f"   {details}"] if details else []),
            f"   {rec.reason}",
            f"   {self._links(rec.job, names)}",
        ]
