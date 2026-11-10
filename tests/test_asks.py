from datetime import date

import pytest
from fakes import MemoryWarningLog

from job_radar.asks import AskBuilder, AskSource, MarketAsks, RequirementNames
from job_radar.checkpoints import FileCheckpoints
from job_radar.history import FileRunHistory
from job_radar.model import (
    AskRow,
    Asks,
    Extraction,
    Job,
    Location,
    Posting,
    Requirement,
    RequirementType,
    RunConfig,
    Window,
    WorkMode,
)
from job_radar.report_renderer import MarkdownRenderer
from job_radar.seen import FileSeenJobs
from job_radar.trends import MarketRuns, RunJobs
from job_radar.words import Words

TODAY = date(2026, 11, 9)  # the month window is 11 Oct to 9 Nov, the one before 11 Sep to 10 Oct
NAMES = RequirementNames()
KEEP = {"extract": "jobs.jsonl"}  # the step whose output is a run's matched jobs
SKILL, TOOL, CERT, YEARS = (
    RequirementType.SKILL,
    RequirementType.TOOL,
    RequirementType.CERTIFICATION,
    RequirementType.YEARS,
)


def asks_for(*names: str, kind: RequirementType = TOOL) -> tuple[Requirement, ...]:
    """Requirements of one type with these names."""
    return tuple(Requirement(type=kind, name=name) for name in names)


def job(
    job_id: str,
    requirements: tuple[Requirement, ...] | None = (),
    posted: date | None = date(2026, 11, 1),
    first_seen: date = TODAY,
) -> Job:
    """A matched job with these requirements; None means its extraction failed."""
    posting = Posting(
        source="demo",
        source_id=job_id,
        title="Engineer",
        company="Acme",
        locations=(Location(text="Remote"),),
        work_mode=WorkMode.REMOTE,
        url=f"https://example.org/{job_id}",
        posted_at=posted,
        description="",
    )
    extraction = (
        None
        if requirements is None
        else Extraction(job_id=job_id, requirements=requirements, prompt_version="t")
    )
    return Job(
        id=job_id, keys=(job_id,), postings=(posting,), first_seen=first_seen, extraction=extraction
    )


def build(jobs, per_type: int = 20, period: str = "month") -> Asks:
    """The section for these jobs, for the window ending today."""
    return AskBuilder(period, per_type, NAMES).build(jobs, TODAY)


def row(asks: Asks, name: str, kind: RequirementType = TOOL) -> AskRow:
    """The row for this requirement."""
    return next(r for r in asks.rows if r.type is kind and r.name == name)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Python", "python"),
        ("Python", "  PYTHON. "),
        ("Python", "Python 3"),
        ("Python", "Python 3.11"),
        ("Java", "Java 17+"),
        ("Python", "Python programming"),
        ("Python", "Python programming language"),
        ("Go", "Go language"),
        ("Go", "Golang"),
        ("PostgreSQL", "Postgres"),
        ("JavaScript", "JS"),
        ("Kubernetes", "k8s"),
        ("Google Cloud", "GCP"),
        ("AWS", "Amazon Web Services"),
        ("scikit-learn", "Scikit Learn"),
        ("CI/CD", "(CI/CD)"),
    ],
)
def test_spellings_of_one_requirement_count_as_one(first, second):
    assert NAMES.key(first) == NAMES.key(second)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("ISO 27001", "ISO"),  # a standard's number is not a version
        (".NET", "NET"),  # a leading dot is part of the name
        ("C++", "C"),
        ("Java", "JavaScript"),
    ],
)
def test_different_requirements_stay_apart(first, second):
    assert NAMES.key(first) != NAMES.key(second)


def test_the_window_is_one_period_ending_on_the_runs_last_day():
    asks = build([])
    assert asks.window == Window(start=date(2026, 10, 11), end=TODAY)
    assert asks.previous == Window(start=date(2026, 9, 11), end=date(2026, 10, 10))
    weeks = build([], period="week")
    assert weeks.window == Window(start=date(2026, 11, 3), end=TODAY)
    assert weeks.previous == Window(start=date(2026, 10, 27), end=date(2026, 11, 2))


def test_a_job_counts_in_the_window_of_its_trend_date():
    asks = build(
        [
            job("in", asks_for("Python"), posted=date(2026, 10, 11)),
            job("before", asks_for("Python"), posted=date(2026, 10, 10)),
            job("too-old", asks_for("Python"), posted=date(2026, 9, 10)),
            job("unposted", asks_for("Python"), posted=None, first_seen=date(2026, 11, 5)),
        ]
    )
    assert (asks.jobs, asks.previous_jobs) == (2, 1)
    assert row(asks, "Python").job_ids == ("in", "unposted")


def test_shares_leave_out_jobs_whose_extraction_failed():
    asks = build(
        [
            job("1", asks_for("Python", "SQL")),
            job("2", asks_for("Python")),
            job("3", ()),  # extracted, asks for nothing known: still in the base
            job("4", None),  # extraction failed: out of the base
        ]
    )
    assert asks.jobs == 3
    assert row(asks, "Python").share == pytest.approx(2 / 3)
    assert row(asks, "SQL").share == pytest.approx(1 / 3)


def test_a_job_counts_once_per_requirement_and_once_across_runs():
    asks = build(
        [
            job("1", asks_for("Python", "python 3")),
            job("1", asks_for("Python")),  # the same job, found again by a later run
            job("2", asks_for("Java")),
        ]
    )
    assert asks.jobs == 2
    assert (row(asks, "Python").jobs, row(asks, "Python").share) == (1, 0.5)


def test_the_most_common_spelling_is_shown():
    asks = build(
        [job("1", asks_for("Postgres")), job("2", asks_for("PostgreSQL"))]
        + [job("3", asks_for("PostgreSQL"))]
    )
    assert [r.name for r in asks.rows] == ["PostgreSQL"]
    assert asks.rows[0].job_ids == ("1", "2", "3")


def test_the_change_is_in_points_against_the_window_before():
    earlier = date(2026, 10, 1)
    asks = build(
        [
            job("1", asks_for("Python")),
            job("2", asks_for("Python")),
            job("3", asks_for("Python", "Rust")),
            job("4", asks_for("SQL")),
            job("5", asks_for("Python"), posted=earlier),
            job("6", asks_for("SQL"), posted=earlier),
        ]
    )
    assert row(asks, "Python").change == pytest.approx(25.0)  # 75% against 50%
    assert row(asks, "SQL").change == pytest.approx(-25.0)  # 25% against 50%
    assert row(asks, "Rust").change == pytest.approx(25.0)  # new: 25% against 0%


def test_with_no_window_before_there_is_no_change_yet():
    asks = build([job("1", asks_for("Python"))])
    assert asks.previous_jobs == 0
    assert row(asks, "Python").change is None


def test_years_rows_show_the_median_years_asked():
    def years(job_id: str, *amounts: int) -> Job:
        """A job asking for Python experience, once per amount."""
        reqs = tuple(Requirement(type=YEARS, name="Python", years=n) for n in amounts)
        return job(job_id, reqs)

    asks = build([years("1", 3), years("2", 5), years("3", 7, 4), years("4", 10)])
    python = row(asks, "Python", YEARS)
    assert python.median_years == 6  # one figure per job, its highest: 3, 5, 7 and 10
    assert row(build([years("1", 2), years("2", 3)]), "Python", YEARS).median_years == 2.5
    unsaid = build([job("1", asks_for("Python", kind=YEARS))])
    assert row(unsaid, "Python", YEARS).median_years is None
    assert "| Python: years not given | 100% (1) |" in render(unsaid)


def test_the_report_lists_the_top_requirements_grouped_by_type_with_their_share():
    jobs = [
        job("1", asks_for("SQL", "Python", "Rust") + asks_for("Writing", kind=SKILL)),
        job("2", asks_for("SQL", "Python") + asks_for("CISSP", kind=CERT)),
        job("3", asks_for("Python", "Excel")),
    ]
    asks = build(jobs, per_type=2)
    assert [(r.type, r.name) for r in asks.rows] == [
        (SKILL, "Writing"),
        (TOOL, "Python"),
        (TOOL, "SQL"),
        (CERT, "CISSP"),
    ]
    ties = build(jobs, per_type=5)
    assert [r.name for r in ties.rows if r.type is TOOL] == ["Python", "SQL", "Excel", "Rust"]


def test_fewer_than_twenty_jobs_is_a_low_sample():
    few = render(build([job(str(n), asks_for("Python")) for n in range(19)]))
    enough = render(build([job(str(n), asks_for("Python")) for n in range(20)]))
    assert "19 matched jobs (low sample)." in few
    assert "20 matched jobs." in enough


def test_market_asks_count_completed_runs_and_this_one():
    class Runs:
        """Two runs: an earlier one and this one."""

        def runs(self):
            return [
                RunJobs(Window(start=TODAY, end=TODAY), None, [job("1", asks_for("Python"))]),
                RunJobs(Window(start=TODAY, end=TODAY), None, [job("2", asks_for("SQL"))]),
            ]

    asks = MarketAsks(Runs(), AskBuilder("month", 20, NAMES), TODAY)
    assert isinstance(asks, AskSource)
    assert {r.name for r in asks.asks().rows} == {"Python", "SQL"}


def test_each_requirement_can_be_traced_back_to_the_postings_it_came_from(tmp_path):
    earlier = tmp_path / "2026-11-05T10-00-00"
    earlier.mkdir()
    done = FileCheckpoints(
        earlier, Window(start=date(2026, 11, 1), end=date(2026, 11, 5)), keep=KEEP
    )
    done.save("extract", [job("1", asks_for("Python"))])
    done.complete()
    now = tmp_path / "2026-11-09T10-00-00"
    now.mkdir()
    window = Window(start=date(2026, 11, 4), end=TODAY)
    this_run = FileCheckpoints(now, window, keep=KEEP)
    this_run.save("extract", [job("2", asks_for("Python"))])
    config = RunConfig(searches=(), sources=())
    history = FileRunHistory(tmp_path, MemoryWarningLog())
    seen = FileSeenJobs(history, tmp_path, MemoryWarningLog())
    runs = MarketRuns(history, seen, this_run, window, config)
    asks = MarketAsks(runs, AskBuilder("month", 20, NAMES), TODAY).asks()
    assert [r.job_ids for r in asks.rows] == [("1", "2")]
    saved = seen.jobs(earlier.name) + this_run.kept(Job)
    traced = [j.postings[0].url for j in saved if j.id in asks.rows[0].job_ids]
    assert traced == ["https://example.org/1", "https://example.org/2"]


def render(asks: Asks) -> str:
    """The what employers ask for section as the report shows it."""
    return "\n".join(MarkdownRenderer(Words())._asks(asks))


def test_the_section_shows_a_table_per_type_with_share_and_change():
    earlier = date(2026, 10, 1)
    jobs = [
        job("1", asks_for("Python") + (Requirement(type=YEARS, name="Python", years=5),)),
        job("2", asks_for("Python", "SQL") + asks_for("system design", kind=SKILL)),
        job("3", asks_for("Python"), posted=earlier),
    ]
    text = render(build(jobs))
    assert text == "\n".join(
        [
            "## What employers ask for",
            "",
            "In the 30 days from 11 Oct to 9 Nov 2026: 2 matched jobs (low sample).",
            "",
            "### Skills",
            "",
            "| Requirement | Share | Change |",
            "|---|---|---|",
            "| system design | 50% (1) | up 50 pts |",
            "",
            "### Tools",
            "",
            "| Requirement | Share | Change |",
            "|---|---|---|",
            "| Python | 100% (2) | no change |",
            "| SQL | 50% (1) | up 50 pts |",
            "",
            "### Years of experience",
            "",
            "| Requirement | Share | Change |",
            "|---|---|---|",
            "| Python: 5 years | 50% (1) | up 50 pts |",
            "",
            "Change: in points, against the 30 days from 11 Sep to 10 Oct 2026 (1 job).",
            "Share: of the matched jobs with requirements; failed extractions left out.",
            "Fewer than 20 jobs in the window is a low sample.",
        ]
    )


def test_the_section_says_when_there_is_no_change_yet():
    text = render(build([job("1", asks_for("Python"))]))
    assert "| Requirement | Share |\n|---|---|\n| Python | 100% (1) |" in text
    assert "No change yet: no matched job with requirements in the 30 days before." in text


def test_the_section_says_when_no_job_has_requirements():
    assert render(build([job("1", None)])) == (
        "## What employers ask for\n\n"
        "No matched job with requirements in the 30 days from 11 Oct to 9 Nov 2026."
    )
