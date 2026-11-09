from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fakes import WINDOW, FakeStats, MemoryWriter, job

from job_radar.model import (
    Job,
    Location,
    Period,
    Posting,
    Recommendation,
    Report,
    ReportContent,
    Salary,
    StepCount,
    Window,
    WorkMode,
)
from job_radar.report_renderer import MarkdownRenderer
from job_radar.steps.report import ReportStep

GOLDEN = Path(__file__).parent / "fixtures" / "report" / "report.md"
RUN = "2026-11-09T13-58-11"
NOV = Window(start=date(2026, 11, 8), end=date(2026, 11, 9))


def posting(source_id: str, title: str, **fields) -> Posting:
    """A posting with the given id and title; any other field can be set."""
    values = dict(
        source="getro",
        source_id=source_id,
        title=title,
        company="Example Org",
        locations=(Location(text="Remote"),),
        work_mode=WorkMode.REMOTE,
        url=f"https://example.org/jobs/{source_id}",
        description="",
    )
    return Posting(**(values | fields))


def rec(score: int, reason: str, *postings: Posting) -> Recommendation:
    """A recommendation for a job made of these postings."""
    one = Job(id=postings[0].key, keys=(), postings=postings, first_seen=date(2026, 11, 9))
    return Recommendation(job=one, score=score, reason=reason)


def content(*recs: Recommendation, funnel: tuple[StepCount, ...] = ()) -> ReportContent:
    """A report's content for the November window, with a minimum score of 40."""
    return ReportContent(run=RUN, window=NOV, min_score=40, recommendations=recs, funnel=funnel)


def salary(low: str | None, high: str | None, currency="USD", period=Period.YEAR) -> Salary:
    """A salary from amounts written as strings."""
    return Salary(
        min=None if low is None else Decimal(low),
        max=None if high is None else Decimal(high),
        currency=currency,
        period=period,
    )


def test_markdown_report_matches_the_golden_file():
    report = content(
        rec(
            86,
            "A hands-on backend role on a small climate team, close to what you want.",
            posting(
                "101",
                "Senior Software Engineer",
                company="Acme Climate",
                locations=(Location(text="Seattle, WA"), Location(text="Remote, US")),
                salary=salary("150000", "180000"),
                posted_at=date(2026, 11, 8),
            ),
            posting("x-7", "Senior Software Engineer", source="jobspipe"),
        ),
        rec(
            61,
            "A data platform role in Berlin; a good field for you but outside your places.",
            posting(
                "102",
                "Data Platform Engineer",
                company="Open Grid",
                locations=(Location(text="Berlin, Germany"),),
                work_mode=WorkMode.HYBRID,
                salary=salary("52500", None, currency="EUR"),
                posted_at=date(2026, 11, 9),
            ),
        ),
        rec(
            40,
            "No description on the board; the title suggests a partial fit.",
            posting(
                "103",
                "Tech Lead",
                company="Civic Signal",
                locations=(),
                work_mode=WorkMode.UNKNOWN,
            ),
        ),
        funnel=(
            StepCount(step="fetch", count=1),
            StepCount(step="convert", count=200),
            StepCount(step="recommend", count=3),
        ),
    )
    assert MarkdownRenderer().render(report) == GOLDEN.read_text(encoding="utf-8")


def test_markdown_report_says_when_no_job_reached_the_minimum():
    text = MarkdownRenderer().render(content())
    assert "## Recommended jobs (0)\n\nNo job scored 40 or more this run.\n" in text
    assert "recommended: 0\n" in text


@pytest.mark.parametrize(
    ("pay", "words"),
    [
        (salary("150000", "180000"), "$150k to $180k a year"),
        (salary("150000", "150000"), "$150k a year"),
        (salary("120000", None), "From $120k a year"),
        (salary(None, "95500"), "Up to $96k a year"),
        (salary("128880", "193320"), "$129k to $193k a year"),
        (salary("45", "60.5", period=Period.HOUR), "$45 to $60.50 an hour"),
        (salary("4000", "5000", currency="GBP", period=Period.MONTH), "GBP 4k to GBP 5k a month"),
    ],
)
def test_salary_in_words(pay, words):
    one = posting("1", "Engineer", salary=pay, work_mode=WorkMode.UNKNOWN, locations=())
    text = MarkdownRenderer().render(content(rec(50, "r", one)))
    assert f"   {words}.\n" in text


def test_a_place_that_only_repeats_the_work_mode_is_left_out():
    one = posting(
        "1", "Engineer", locations=(Location(text="Remote"),), posted_at=date(2026, 11, 6)
    )
    assert "   Remote. Posted 6 Nov.\n" in MarkdownRenderer().render(content(rec(50, "r", one)))


@pytest.mark.parametrize(
    ("window", "words"),
    [
        (Window(start=date(2026, 11, 9), end=date(2026, 11, 9)), "from 9 Nov 2026."),
        (Window(start=date(2026, 12, 28), end=date(2027, 1, 3)), "from 28 Dec 2026 to 3 Jan 2027."),
    ],
)
def test_window_in_words(window, words):
    report = ReportContent(run=RUN, window=window, min_score=40, recommendations=(), funnel=())
    assert f"Covers postings {words}\n" in MarkdownRenderer().render(report)


class KeepingRenderer:
    """A renderer that keeps the content it was given."""

    def __init__(self):
        self.content: ReportContent | None = None

    def render(self, content: ReportContent) -> str:
        self.content = content
        return "the report"


def test_report_step_puts_the_run_into_the_content_and_writes_the_rendered_text():
    renderer, writer = KeepingRenderer(), MemoryWriter()
    funnel = [StepCount(step="fetch", count=2), StepCount(step="convert", count=12)]
    recs = [Recommendation(job=job("1"), score=90, reason="Fits well")]
    reports = ReportStep(FakeStats(funnel), renderer, writer, RUN, WINDOW, 40).run(recs)
    assert renderer.content == ReportContent(
        run=RUN, window=WINDOW, min_score=40, recommendations=tuple(recs), funnel=tuple(funnel)
    )
    assert writer.text == "the report"
    assert reports == [Report(location="memory/report.md", summary="1 job recommended")]
