from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fakes import (
    WINDOW,
    FakeStats,
    MemoryPendingLog,
    MemorySourceCountLog,
    MemorySpendLog,
    MemoryWarningLog,
    MemoryWriter,
    NoAsks,
    NoGaps,
    NoTrends,
    SetKeptJobs,
    grouper,
    job,
)

from job_radar.app.run_result import RunSucceeded
from job_radar.models import (
    Alert,
    AlertCode,
    Approval,
    Classification,
    Job,
    Location,
    Opening,
    OpeningGroup,
    Period,
    Posting,
    Recommendation,
    Report,
    ReportContent,
    Salary,
    Seniority,
    SourceCount,
    SourceSummary,
    Spend,
    SpendDecision,
    StepCount,
    Window,
    WorkMode,
)
from job_radar.pipeline.steps.report import ReportStep
from job_radar.report.report_renderer import MarkdownRenderer
from job_radar.report.words import Words

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


SOURCES = (
    SourceSummary(source="getro", name="Fast Forward", postings=200),
    SourceSummary(source="jobspipe", name="JobsPipe", postings=18, credits=18),
)
APPROVAL = Approval(
    source="jobspipe", estimate=18, decision=SpendDecision.AUTO, cap=20, credits_before=862
)


def test_markdown_report_matches_the_golden_file():
    first = rec(
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
    )
    second = rec(
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
    )
    third = rec(
        40,
        "No description on the board; the title suggests a partial fit.",
        posting(
            "103", "Tech Lead", company="Civic Signal", locations=(), work_mode=WorkMode.UNKNOWN
        ),
    )
    analyst = rec(
        0,
        "",
        posting(
            "104",
            "Data Analyst",
            company="Riverbend Health",
            locations=(Location(text="Chicago, IL"),),
            work_mode=WorkMode.ONSITE,
            posted_at=date(2026, 11, 8),
        ),
    ).job
    report = ReportContent(
        run=RUN,
        window=NOV,
        sources=SOURCES,
        min_score=40,
        recommendations=(first, second, third),
        openings=(
            OpeningGroup(
                name="engineering",
                openings=(
                    Opening(job=second.job, score=61),
                    Opening(job=first.job, score=86),
                ),
            ),
            OpeningGroup(name="data", openings=(Opening(job=analyst),)),
            OpeningGroup(name="Not labelled", openings=(Opening(job=third.job, score=40),)),
        ),
        funnel=(
            StepCount(step="fetch", count=2),
            StepCount(step="convert", count=218),
            StepCount(step="recommend", count=3),
        ),
        spends=(Spend(approval=APPROVAL, charged=18, credits_after=844),),
    )
    assert MarkdownRenderer(Words()).render(report) == GOLDEN.read_text(encoding="utf-8")


def test_markdown_report_says_when_no_job_reached_the_minimum():
    text = MarkdownRenderer(Words()).render(content())
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
    text = MarkdownRenderer(Words()).render(content(rec(50, "r", one)))
    assert f"   {words}.\n" in text


def test_a_place_that_only_repeats_the_work_mode_is_left_out():
    one = posting(
        "1", "Engineer", locations=(Location(text="Remote"),), posted_at=date(2026, 11, 6)
    )
    assert "   Remote. Posted 6 Nov.\n" in MarkdownRenderer(Words()).render(
        content(rec(50, "r", one))
    )


@pytest.mark.parametrize(
    ("window", "words"),
    [
        (Window(start=date(2026, 11, 9), end=date(2026, 11, 9)), "from 9 Nov 2026."),
        (Window(start=date(2026, 12, 28), end=date(2027, 1, 3)), "from 28 Dec 2026 to 3 Jan 2027."),
    ],
)
def test_window_in_words(window, words):
    report = ReportContent(run=RUN, window=window, min_score=40, recommendations=(), funnel=())
    assert f"Covers postings {words}\n" in MarkdownRenderer(Words()).render(report)


class KeepingRenderer:
    """A renderer that keeps the content it was given."""

    def __init__(self):
        self.content: ReportContent | None = None

    def render(self, content: ReportContent) -> str:
        self.content = content
        return "the report"


def report_step(
    renderer,
    writer=None,
    funnel=(),
    spends=(),
    counts=(),
    jobs=(),
    sources=None,
    group_by="job_type",
    warnings=None,
) -> ReportStep:
    """A report step over these parts, with nothing to show for trends, asks and gaps."""
    return ReportStep(
        FakeStats(list(funnel)),
        renderer,
        writer or MemoryWriter(),
        MemorySpendLog(*spends),
        MemoryPendingLog(),
        NoTrends(),
        NoAsks(),
        NoGaps(),
        RUN,
        WINDOW,
        None,
        40,
        {"demo": "Demo board"} if sources is None else sources,
        MemorySourceCountLog(*counts),
        SetKeptJobs(*jobs),
        grouper(group_by),
        warnings if warnings is not None else MemoryWarningLog(),
    )


def test_report_step_puts_the_run_into_the_content_and_writes_the_rendered_text():
    renderer, writer = KeepingRenderer(), MemoryWriter()
    funnel = [StepCount(step="fetch", count=2), StepCount(step="convert", count=12)]
    recs = [Recommendation(job=job("1"), score=90, reason="Fits well")]
    reports = report_step(
        renderer, writer, funnel, counts=[SourceCount(source="demo", postings=12)], jobs=[job("1")]
    ).run(recs)
    assert renderer.content == ReportContent(
        run=RUN,
        window=WINDOW,
        sources=(SourceSummary(source="demo", name="Demo board", postings=12),),
        min_score=40,
        recommendations=tuple(recs),
        openings=(OpeningGroup(name="Not labelled", openings=(Opening(job=job("1"), score=90),)),),
        funnel=tuple(funnel),
    )
    assert writer.text == "the report"
    assert reports == [
        Report(location="memory/report.md", summary="1 new opening, 1 recommended, 0 alerts")
    ]


def test_a_long_break_is_noted_with_the_days_left_out():
    gap = Window(start=date(2026, 10, 21), end=date(2026, 10, 25))
    window = Window(start=date(2026, 10, 26), end=date(2026, 11, 9))
    report = ReportContent(
        run=RUN, window=window, not_covered=gap, min_score=40, recommendations=(), funnel=()
    )
    text = MarkdownRenderer(Words()).render(report)
    assert "covers: [2026-10-26, 2026-11-09]\nnot_covered: [2026-10-21, 2026-10-25]\n" in text
    assert (
        "Covers postings from 26 Oct to 9 Nov 2026.\n\nNot covered: 21 Oct to 25 Oct 2026. "
        "The last run was on 20 Oct, and a run reaches back at most 14 days.\n"
    ) in text


def test_no_gap_means_no_note():
    text = MarkdownRenderer(Words()).render(content())
    assert "not_covered" not in text and "Not covered" not in text


def test_the_report_says_what_each_paid_source_spent():
    approval = Approval(
        source="jobspipe", estimate=18, decision=SpendDecision.AUTO, cap=20, credits_before=862
    )
    skipped = approval.model_copy(update={"decision": SpendDecision.SKIPPED, "cap": 0})
    spends = (Spend(approval=approval, charged=18, credits_after=844), Spend(approval=skipped))
    report = ReportContent(
        run=RUN,
        window=NOV,
        sources=SOURCES,
        min_score=40,
        recommendations=(),
        funnel=(),
        spends=spends,
    )
    text = MarkdownRenderer(Words()).render(report)
    assert (
        "Paid sources:\n\n"
        "- JobsPipe: estimate 18 credits, within every limit. 18 used, 844 left.\n"
        "- JobsPipe: estimate 18 credits, skipped by you. 862 credits left.\n"
    ) in text


def test_the_header_lists_each_source_with_its_postings_and_credits():
    sources = (
        SourceSummary(source="getro", name="Fast Forward", postings=1478),
        SourceSummary(source="jobspipe", name="JobsPipe", postings=1, credits=1),
    )
    report = ReportContent(
        run=RUN, window=NOV, sources=sources, min_score=40, recommendations=(), funnel=()
    )
    text = MarkdownRenderer(Words()).render(report)
    assert "\nSources: Fast Forward 1,478 postings, JobsPipe 1 posting (1 credit).\n" in text
    assert "sources: {getro: 1478, jobspipe: 1}\n" in text


def test_a_skipped_paid_source_says_so_in_the_header():
    skipped = SourceSummary(source="jobspipe", name="JobsPipe", postings=0, skipped=True)
    report = ReportContent(
        run=RUN, window=NOV, sources=(skipped,), min_score=40, recommendations=(), funnel=()
    )
    assert "\nSources: JobsPipe skipped by you.\n" in MarkdownRenderer(Words()).render(report)


def test_the_report_step_counts_postings_per_source_and_credits_from_the_spend_log():
    renderer = KeepingRenderer()
    skipped = APPROVAL.model_copy(update={"source": "paid", "decision": SpendDecision.SKIPPED})
    report_step(
        renderer,
        counts=[
            SourceCount(source="getro", postings=200),
            SourceCount(source="jobspipe", postings=18),
        ],
        spends=[Spend(approval=APPROVAL, charged=18, credits_after=844), Spend(approval=skipped)],
        sources={"getro": "Fast Forward", "jobspipe": "JobsPipe", "paid": "Paid board"},
    ).run([])
    assert renderer.content.sources == (
        SourceSummary(source="getro", name="Fast Forward", postings=200),
        SourceSummary(source="jobspipe", name="JobsPipe", postings=18, credits=18),
        SourceSummary(source="paid", name="Paid board", postings=0, skipped=True),
    )


def test_with_no_alerts_the_section_says_none():
    text = MarkdownRenderer(Words()).render(content())
    assert "\n## Alerts\n\nNone.\n\n## Recommended jobs (0)\n" in text
    assert "alerts: 0\n" in text


def test_alerts_are_listed_at_the_top():
    report = ReportContent(
        run=RUN,
        window=NOV,
        alerts=(Alert(code=AlertCode.SOURCE_EMPTY, message="JobsPipe returned no postings"),),
        min_score=40,
        recommendations=(),
        funnel=(),
    )
    text = MarkdownRenderer(Words()).render(report)
    assert "## Alerts\n\n- JobsPipe returned no postings\n" in text
    assert "alerts: 1\n" in text


def test_the_report_lists_every_new_matching_job_by_group():
    # Acceptance: by default, the report lists every matching posting not seen in an earlier run.
    jobs = [job("1", "Data Engineer"), job("2", "Platform Engineer")]
    labels = {"demo:1": "engineering", "demo:2": "data"}
    jobs = [
        j.model_copy(
            update={
                "classification": Classification(
                    job_id=j.id,
                    seniority=Seniority.UNKNOWN,
                    job_type=labels[j.id],
                    prompt_version="test",
                )
            }
        )
        for j in jobs
    ]
    writer = MemoryWriter()
    [report] = report_step(MarkdownRenderer(Words()), writer, jobs=jobs).run([])
    assert (
        "## New openings (2)\n\n"
        "### engineering (1)\n\n"
        "- **Data Engineer**, Example Org. Remote. "
        "[Demo board](https://example.org/jobs/1)\n\n"
        "### data (1)\n\n"
        "- **Platform Engineer**, Example Org. Remote. "
        "[Demo board](https://example.org/jobs/2)\n"
    ) in writer.text
    assert "new_openings: 2\n" in writer.text
    assert report.summary == "2 new openings, 0 recommended, 0 alerts"


def test_with_no_new_openings_the_section_says_so():
    text = MarkdownRenderer(Words()).render(content())
    assert "## New openings (0)\n\nNo new job matched your searches this run.\n" in text


def test_groups_inside_groups_get_a_lower_heading():
    one = job("1")
    report = ReportContent(
        run=RUN,
        window=NOV,
        min_score=40,
        recommendations=(),
        openings=(
            OpeningGroup(
                name="engineering",
                groups=(OpeningGroup(name="climate", openings=(Opening(job=one, score=55),)),),
            ),
        ),
        funnel=(),
    )
    assert (
        "## New openings (1)\n\n### engineering (1)\n\n#### climate (1)\n\n"
        "- **Data Engineer**, Example Org. Remote. Recommended, score 55. "
        "[demo](https://example.org/jobs/1)\n"
    ) in MarkdownRenderer(Words()).render(report)


def test_each_job_shows_title_company_location_or_remote_salary_if_posted_source_and_link():
    # Acceptance (Job search): each job in the report shows title, company, location or
    # remote, salary if posted, source, and a link to the posting.
    onsite = posting(
        "1",
        "Data Engineer",
        locations=(Location(text="Oakland, CA"),),
        work_mode=WorkMode.ONSITE,
        salary=salary("120000", "150000"),
    )
    remote = posting("x-2", "Platform Engineer", source="jobspipe")
    first = rec(80, "Fits.", onsite)
    second = Job(id="b", keys=(), postings=(remote,), first_seen=date(2026, 11, 9))
    report = ReportContent(
        run=RUN,
        window=NOV,
        sources=SOURCES,
        min_score=40,
        recommendations=(first,),
        openings=(
            OpeningGroup(
                name="Other", openings=(Opening(job=first.job, score=80), Opening(job=second))
            ),
        ),
        funnel=(),
    )
    text = MarkdownRenderer(Words()).render(report)
    assert (
        "1. **Data Engineer**, Example Org (score 80)\n"
        "   On-site. Oakland, CA. $120k to $150k a year.\n"
        "   Fits.\n"
        "   [Fast Forward](https://example.org/jobs/1)\n"
    ) in text
    assert (
        "- **Data Engineer**, Example Org. On-site. Oakland, CA. $120k to $150k a year. "
        "Recommended, score 80. [Fast Forward](https://example.org/jobs/1)\n"
        "- **Platform Engineer**, Example Org. Remote. [JobsPipe](https://example.org/jobs/x-2)\n"
    ) in text


def test_links_carry_the_source_name_for_people():
    both = rec(70, "r", posting("1", "Engineer"), posting("x-1", "Engineer", source="jobspipe"))
    report = ReportContent(
        run=RUN,
        window=NOV,
        sources=SOURCES[:1],
        min_score=40,
        recommendations=(both,),
        openings=(OpeningGroup(name="Other", openings=(Opening(job=both.job, score=70),)),),
        funnel=(),
    )
    text = MarkdownRenderer(Words()).render(report)
    links = "[Fast Forward](https://example.org/jobs/1), [jobspipe](https://example.org/jobs/x-1)"
    assert f"   {links}\n" in text
    assert f"Recommended, score 70. {links}\n" in text


def test_every_section_is_there_even_with_nothing_to_show():
    text = MarkdownRenderer(Words()).render(content())
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Alerts",
        "## Recommended jobs (0)",
        "## New openings (0)",
        "## Market trends",
        "## What employers ask for",
        "## Experience to gain",
        "## About this run",
    ]


@pytest.mark.parametrize(
    ("openings", "recommended", "summary", "alerts"),
    [
        (0, 0, "0 new openings, 0 recommended, 1 alert", "- No new jobs matched your searches.\n"),
        (1, 1, "1 new opening, 1 recommended, 0 alerts", ""),
        (23, 10, "23 new openings, 10 recommended, 0 alerts", ""),
    ],
)
def test_the_terminal_summary_counts_openings_recommended_jobs_and_alerts(
    openings, recommended, summary, alerts
):
    jobs = [job(str(n)) for n in range(openings)]
    recs = [Recommendation(job=j, score=50, reason="r") for j in jobs[:recommended]]
    [report] = report_step(KeepingRenderer(), jobs=jobs).run(recs)
    assert report.summary == summary
    message = RunSucceeded(
        location=report.location, summary=report.summary, alerts=report.alerts
    ).message()
    assert message == f"Run finished: {summary}.\n{alerts}Report: memory/report.md"
