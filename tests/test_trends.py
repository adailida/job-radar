from datetime import date
from decimal import Decimal

import pytest

from job_radar.checkpoints import FileCheckpoints
from job_radar.history import FileRunHistory
from job_radar.model import (
    Classification,
    Job,
    Location,
    Period,
    Posting,
    RunConfig,
    Salary,
    Search,
    Seniority,
    TrendChange,
    TrendNote,
    TrendPeriod,
    Trends,
    Window,
    WorkMode,
)
from job_radar.report_renderer import MarkdownRenderer
from job_radar.trends import MarketRuns, MarketTrends, RunJobs, TrendBuilder
from job_radar.words import Words

MONTHS = TrendBuilder("month")


def job(
    job_id: str,
    posted: date | None = date(2026, 11, 3),
    mode: WorkMode = WorkMode.REMOTE,
    salary: Salary | None = None,
    level: Seniority | None = None,
    first_seen: date = date(2026, 11, 9),
) -> Job:
    """A matched job with these facts."""
    posting = Posting(
        source="demo",
        source_id=job_id,
        title="Engineer",
        company="Acme",
        locations=(Location(text="Remote"),),
        work_mode=mode,
        salary=salary,
        url=f"https://example.org/{job_id}",
        posted_at=posted,
        description="",
    )
    labels = Classification(job_id=job_id, seniority=level, prompt_version="t") if level else None
    return Job(
        id=job_id,
        keys=(job_id,),
        postings=(posting,),
        first_seen=first_seen,
        classification=labels,
    )


def pay(low, high, period=Period.YEAR, currency="USD") -> Salary:
    """A pay range."""
    return Salary(
        min=None if low is None else Decimal(low),
        max=None if high is None else Decimal(high),
        currency=currency,
        period=period,
    )


def run(start: date, end: date, jobs=(), config: RunConfig | None = None) -> RunJobs:
    """A run with this window and these jobs."""
    return RunJobs(Window(start=start, end=end), config, jobs)


@pytest.mark.parametrize(
    ("kind", "day", "span"),
    [
        ("month", date(2026, 11, 9), (date(2026, 11, 1), date(2026, 11, 30))),
        ("week", date(2026, 11, 9), (date(2026, 11, 9), date(2026, 11, 15))),
        ("week", date(2026, 11, 8), (date(2026, 11, 2), date(2026, 11, 8))),
        ("quarter", date(2026, 11, 9), (date(2026, 10, 1), date(2026, 12, 31))),
        ("quarter", date(2026, 2, 3), (date(2026, 1, 1), date(2026, 3, 31))),
    ],
)
def test_periods(kind, day, span):
    assert TrendBuilder(kind).period_of(day) == span


def test_a_job_counts_on_its_earliest_posted_date_else_when_first_seen():
    one = job("1", posted=date(2026, 11, 3))
    two = one.postings[0].model_copy(update={"posted_at": date(2026, 10, 30)})
    assert TrendBuilder.trend_date(
        one.model_copy(update={"postings": (one.postings[0], two)})
    ) == date(2026, 10, 30)
    assert TrendBuilder.trend_date(job("2", posted=None)) == date(2026, 11, 9)


def test_coverage_marks_partial_periods_and_postings_count_per_covered_day():
    trends = MONTHS.build(
        [
            run(date(2026, 10, 26), date(2026, 11, 9), [job("1"), job("2")]),
            run(date(2026, 10, 1), date(2026, 10, 10), [job("3", posted=date(2026, 10, 5))]),
        ]
    )
    october, november = trends.periods
    assert (october.covered_days, october.partial, october.postings) == (16, True, 1)
    assert (november.covered_days, november.days, november.partial) == (9, 30, True)
    assert november.per_day == pytest.approx(2 / 9)


def test_a_job_found_by_two_runs_counts_once():
    trends = MONTHS.build(
        [
            run(date(2026, 11, 1), date(2026, 11, 5), [job("1")]),
            run(date(2026, 11, 4), date(2026, 11, 9), [job("1"), job("2")]),
        ]
    )
    assert trends.periods[-1].postings == 2


def test_work_mode_shares_leave_out_jobs_that_dont_say():
    jobs = [
        job("1", mode=WorkMode.REMOTE),
        job("2", mode=WorkMode.REMOTE),
        job("3", mode=WorkMode.ONSITE),
        job("4", mode=WorkMode.UNKNOWN),
    ]
    [november] = MONTHS.build([run(date(2026, 11, 1), date(2026, 11, 9), jobs)]).periods
    assert november.work_modes == {"remote": pytest.approx(2 / 3), "onsite": pytest.approx(1 / 3)}
    assert (november.work_mode_base, november.work_mode_unknown) == (3, 1)


def test_salary_quartiles_from_yearly_usd_midpoints():
    jobs = [
        job("1", salary=pay(100000, 140000)),
        job("2", salary=pay(60, 60, period=Period.HOUR)),
        job("3", salary=pay(None, 15000, period=Period.MONTH)),
        job("4", salary=pay(200000, 200000, currency="EUR")),
        job("5"),
    ]
    [november] = MONTHS.build([run(date(2026, 11, 1), date(2026, 11, 9), jobs)]).periods
    assert november.salary_base == 3
    assert (november.salary_p25, november.salary_median, november.salary_p75) == (
        122400,
        124800,
        152400,
    )
    assert november.salary_listed == pytest.approx(4 / 5)


def test_seniority_mix_leaves_out_unknown_and_unlabelled_jobs():
    jobs = [
        job("1", level=Seniority.SENIOR),
        job("2", level=Seniority.SENIOR),
        job("3", level=Seniority.LEAD),
        job("4", level=Seniority.UNKNOWN),
        job("5"),
    ]
    [november] = MONTHS.build([run(date(2026, 11, 1), date(2026, 11, 9), jobs)]).periods
    assert november.seniority == {"senior": pytest.approx(2 / 3), "lead": pytest.approx(1 / 3)}
    assert (november.seniority_base, november.seniority_unknown) == (3, 2)


def test_only_the_last_six_periods_with_a_covered_day_are_shown():
    trends = TrendBuilder("month").build([run(date(2026, 1, 1), date(2026, 11, 9))])
    assert [p.start.month for p in trends.periods] == [6, 7, 8, 9, 10, 11]


def test_the_latest_period_is_compared_with_the_last_complete_one():
    october = [job(str(n), posted=date(2026, 10, 10), mode=WorkMode.REMOTE) for n in range(31)]
    november = [job(f"n{n}", posted=date(2026, 11, 2), mode=WorkMode.ONSITE) for n in range(18)]
    trends = MONTHS.build([run(date(2026, 10, 1), date(2026, 11, 9), october + november)])
    change = trends.change
    assert change.against == date(2026, 10, 1)
    assert change.per_day == pytest.approx((18 / 9 - 31 / 31) / (31 / 31) * 100)
    assert change.work_modes == {"onsite": pytest.approx(100), "remote": pytest.approx(-100)}


def test_nothing_to_compare_without_a_complete_period_before_the_latest():
    assert MONTHS.build([run(date(2026, 11, 1), date(2026, 11, 9))]).change is None
    two_partial = MONTHS.build([run(date(2026, 10, 26), date(2026, 11, 9))])
    assert len(two_partial.periods) == 2 and two_partial.change is None


def config(sources=("getro",), **searches: Search) -> RunConfig:
    """What a run searched for and where."""
    return RunConfig(searches=tuple(searches.values()), sources=tuple(sources))


def test_changes_to_sources_and_searches_are_noted_from_the_first_period_shown():
    old = config(remote=Search(name="remote"), seattle=Search(name="seattle"))
    new = config(
        ("getro", "jobspipe"),
        remote=Search(name="remote", roles=("engineer",)),
        lead=Search(name="lead"),
    )
    trends = MONTHS.build(
        [
            run(date(2026, 11, 1), date(2026, 11, 5), config=old),
            run(date(2026, 11, 8), date(2026, 11, 9), config=new),
            run(date(2026, 11, 9), date(2026, 11, 9), config=None),
        ]
    )
    assert trends.notes == (
        TrendNote(
            day=date(2026, 11, 9),
            changes=(
                "added source jobspipe",
                "added search lead",
                "removed search seattle",
                "changed search remote",
            ),
        ),
    )


def test_a_change_before_the_periods_shown_is_not_noted():
    later = config(("jobspipe",))
    runs = [
        run(date(2026, 1, 5), date(2026, 1, 6), config=config()),
        run(date(2026, 2, 5), date(2026, 2, 6), config=later),
        *(run(date(2026, m, 5), date(2026, m, 6), config=later) for m in range(6, 12)),
    ]
    trends = MONTHS.build(runs)
    assert [p.start.month for p in trends.periods] == [6, 7, 8, 9, 10, 11]
    assert trends.notes == ()


def test_the_manifest_keeps_the_runs_config_and_history_reads_it(tmp_path):
    folder = tmp_path / "2026-11-09T10-00-00"
    folder.mkdir()
    saved = config(("getro", "jobspipe"), remote=Search(name="remote"))
    FileCheckpoints(
        folder, Window(start=date(2026, 11, 8), end=date(2026, 11, 9)), config=saved
    ).save("fetch", [])
    assert FileRunHistory(tmp_path).runs()[0].config == saved


def test_kept_output_reads_the_step_file_before_the_run_completes_and_the_kept_file_after(tmp_path):
    checkpoints = FileCheckpoints(
        tmp_path,
        Window(start=date(2026, 11, 8), end=date(2026, 11, 9)),
        keep={"extract": "jobs.jsonl"},
    )
    assert checkpoints.kept(Job) == []
    checkpoints.save("extract", [job("1")])
    assert [j.id for j in checkpoints.kept(Job)] == ["1"]
    checkpoints.complete()
    assert [j.id for j in checkpoints.kept(Job)] == ["1"]


def test_market_trends_add_this_run_to_the_completed_ones(tmp_path):
    earlier = tmp_path / "2026-11-05T10-00-00"
    earlier.mkdir()
    done = FileCheckpoints(
        earlier,
        Window(start=date(2026, 11, 1), end=date(2026, 11, 5)),
        keep={"extract": "jobs.jsonl"},
    )
    done.save("extract", [job("1", posted=date(2026, 11, 2))])
    done.complete()
    now = tmp_path / "2026-11-09T10-00-00"
    now.mkdir()
    window = Window(start=date(2026, 11, 4), end=date(2026, 11, 9))
    this_run = FileCheckpoints(now, window, keep={"extract": "jobs.jsonl"})
    this_run.save("extract", [job("2")])
    runs = MarketRuns(FileRunHistory(tmp_path), tmp_path, this_run, window, config())
    trends = MarketTrends(runs, MONTHS).trends()
    assert (trends.periods[-1].postings, trends.periods[-1].covered_days) == (2, 9)


def period(start: date, end: date, covered: int, postings: int, **figures) -> TrendPeriod:
    """A trend period with these figures and quiet defaults for the rest."""
    values = dict(
        start=start,
        end=end,
        covered_days=covered,
        postings=postings,
        per_day=postings / covered,
        work_modes={"remote": 0.5, "onsite": 0.5},
        work_mode_base=postings,
        work_mode_unknown=0,
        salary_median=150000,
        salary_p25=130000,
        salary_p75=170000,
        salary_base=postings,
        salary_listed=0.5,
        seniority={"senior": 1.0},
        seniority_base=postings,
        seniority_unknown=0,
    )
    return TrendPeriod(**(values | figures))


def test_the_trends_section_renders_periods_change_notes_and_low_samples():
    october = period(date(2026, 10, 1), date(2026, 10, 31), 31, 31)
    november = period(
        date(2026, 11, 1),
        date(2026, 11, 30),
        9,
        18,
        work_modes={"remote": 0.6, "onsite": 0.4},
        salary_median=156000,
        seniority={"senior": 0.5, "lead": 0.5},
    )
    trends = Trends(
        period="month",
        periods=(october, november),
        change=TrendChange(
            against=date(2026, 10, 1),
            per_day=100.0,
            work_modes={"remote": 10.0, "onsite": -10.0},
            salary_median=4.0,
            seniority={"senior": -50.0, "lead": 50.0},
        ),
        notes=(TrendNote(day=date(2026, 11, 9), changes=("added source jobspipe",)),),
        low_sample=20,
    )
    text = "\n".join(MarkdownRenderer(Words())._trends(trends))
    assert text == (
        "## Market trends (by month)\n"
        "\n"
        "Note: 9 Nov: added source jobspipe.\n"
        "\n"
        "|  | Oct | Nov (partial, 9 of 30 days) | Change |\n"
        "|---|---|---|---|\n"
        "| New postings per covered day | 1.0 | 2.0 (low sample) | up 100% |\n"
        "| Postings | 31 | 18 |  |\n"
        "| Remote | 50% | 60% (low sample) | up 10 pts |\n"
        "| On-site | 50% | 40% (low sample) | down 10 pts |\n"
        "| Work mode not given (jobs) | 0 | 0 |  |\n"
        "| Salary median, USD a year | $150k | $156k (low sample) | up 4% |\n"
        "| Salary, 25th to 75th percentile | $130k to $170k | $130k to $170k |  |\n"
        "| Listing a salary | 50% | 50% |  |\n"
        "| Seniority: senior | 100% | 50% (low sample) | down 50 pts |\n"
        "| Seniority: lead | 0% | 50% (low sample) | up 50 pts |\n"
        "| Seniority not known (jobs) | 0 | 0 |  |\n"
        "\n"
        "Change: the latest month against Oct, per covered day.\n"
        "A figure on fewer than 20 jobs is marked as a low sample."
    )


def test_a_single_period_says_there_is_nothing_to_compare():
    trends = MONTHS.build([run(date(2026, 11, 1), date(2026, 11, 9), [job("1")])])
    text = "\n".join(MarkdownRenderer(Words())._trends(trends))
    assert "Nothing to compare yet: the change needs a complete month before the latest." in text
    assert "| Change |" not in text
