import json
from datetime import date

import pytest
from fakes import (
    EXAMPLE,
    FakePrompter,
    FixedClock,
    MemoryCoverage,
    MemoryPendingLog,
    MemorySourceCountLog,
    MemorySpendLog,
    MemoryWarningLog,
    guard,
    job,
    posting,
)
from test_cost import CRITERIA, WINDOW, Planned, approval, plan
from test_report import KeepingRenderer, report_step

from job_radar.app.app_factory import AppFactory
from job_radar.app.cost_check import CostCheck
from job_radar.cli import Cli
from job_radar.config.settings import SettingsFile
from job_radar.llm.job_ranker import KeywordRanker
from job_radar.llm.llm import LlmError, UsageLimit
from job_radar.llm.usage_limit_guard import UsageLimitGuard, UsageLimitReached
from job_radar.models import (
    Alert,
    AlertCode,
    AskRow,
    Asks,
    CandidateProfile,
    PaidFetch,
    RawPage,
    Recommendation,
    RequirementType,
    RunWindows,
    SpendDecision,
)
from job_radar.pipeline.steps.convert import ConvertStep
from job_radar.pipeline.steps.fetch import FetchStep, NoSourceData
from job_radar.pipeline.steps.recommend import RecommendTopJobsStep
from job_radar.report.asks import RequirementNames
from job_radar.report.gaps import CvGaps, GapBuilder
from job_radar.sources.board_client import BoardError
from job_radar.sources.demo import DemoSource
from job_radar.storage.checkpoints import FileCheckpoints
from job_radar.storage.run_history import FileRunHistory
from job_radar.storage.seen_jobs import FileSeenJobs
from job_radar.storage.warning_log import FileWarningLog, TerminalWarnings

FIRST_RUN = "2026-11-05T10-00-00"


class Board:
    """A free board that gives one page, gives nothing, or fails."""

    def __init__(self, name: str, label: str, pages: int = 1, error: Exception | None = None):
        self.name, self.label, self._pages, self._error = name, label, pages, error

    def fetch(self, criteria, window) -> list[RawPage]:
        if self._error:
            raise self._error
        return [RawPage(source=self.name, page=n, body="") for n in range(1, self._pages + 1)]


def fetch(*sources, approvals=(), low_credits=100):
    """Run the fetch step over these boards; its pages and the warnings it recorded."""
    warnings = MemoryWarningLog()
    step = FetchStep(
        sources,
        CRITERIA,
        RunWindows(window=WINDOW),
        approvals,
        MemorySpendLog(),
        warnings,
        low_credits,
        MemoryCoverage(),
    )
    return step.run([]), warnings


def test_warnings_let_the_run_finish_when_a_source_failed():
    # Acceptance (Problem alerts): warnings let the run finish: a source failed.
    down = Board("jobspipe", "JobsPipe", error=BoardError("HTTP 503 after 3 retries"))
    pages, warnings = fetch(down, Board("getro", "Fast Forward"))
    assert [page.source for page in pages] == ["getro"]
    assert warnings.alerts() == [
        Alert(
            code=AlertCode.SOURCE_FAILED,
            message="JobsPipe failed: HTTP 503 after 3 retries. Its postings are not in this run.",
        )
    ]


def test_a_source_that_fails_unexpectedly_is_named_with_its_error_type():
    broken = Board("getro", "Fast Forward", error=KeyError("results"))
    _, warnings = fetch(broken, Board("demo", "Demo board"))
    assert warnings.messages() == [
        "Fast Forward failed: KeyError: 'results'. Its postings are not in this run."
    ]


def test_errors_stop_the_run_with_a_clear_message_when_no_source_is_reachable():
    # Acceptance (Problem alerts): errors stop the run with a clear message: no source reachable.
    jobspipe = Board("jobspipe", "JobsPipe", error=BoardError("no answer in time after 3 retries"))
    getro = Board("getro", "Fast Forward", error=BoardError("HTTP 503 after 3 retries"))
    with pytest.raises(NoSourceData) as stopped:
        fetch(jobspipe, getro)
    assert str(stopped.value) == (
        "No source returned data: JobsPipe failed (no answer in time after 3 retries), "
        "Fast Forward failed (HTTP 503 after 3 retries)"
    )


def test_a_source_skipped_by_you_is_a_warning_and_alone_doesnt_stop_the_run():
    skipped = approval(SpendDecision.SKIPPED, cap=0)
    pages, warnings = fetch(Planned(plan()), approvals=[skipped])
    assert pages == []
    assert warnings.messages() == [
        "JobsPipe skipped by you at the cost check: its postings are not in this run."
    ]


def test_warnings_let_the_run_finish_when_a_source_returned_nothing():
    # Acceptance (Problem alerts): warnings let the run finish: a source returned nothing.
    _, warnings = fetch(Board("getro", "Fast Forward", pages=0), Board("demo", "Demo board"))
    assert warnings.alerts() == [
        Alert(code=AlertCode.SOURCE_EMPTY, message="Fast Forward returned no postings.")
    ]


def test_a_board_whose_pages_hold_no_postings_is_a_warning():
    class NoPostings:
        source = "getro"

        def parse(self, page):
            return []

    class OnePosting:
        source = "demo"

        def parse(self, page):
            return [posting(str(page.page))]

    warnings = MemoryWarningLog()
    step = ConvertStep(
        {"getro": NoPostings(), "demo": OnePosting()},
        MemorySourceCountLog(),
        warnings,
        {"getro": "Fast Forward", "demo": "Demo board"},
    )
    step.run([RawPage(source="getro", page=1, body=""), RawPage(source="demo", page=1, body="")])
    assert warnings.messages() == ["Fast Forward returned no postings."]


class Paying:
    """A paid source that charges a set amount and leaves a set number of credits."""

    name, label = "jobspipe", "JobsPipe"

    def __init__(self, charged: int, left: int):
        self._charged, self._left = charged, left

    def plan(self, criteria, window):
        return plan()

    def fetch(self, criteria, window):
        return []

    def fetch_paid(self, criteria, window, cap, counts=()):
        page = RawPage(source=self.name, page=1, body="{}")
        return PaidFetch(pages=(page,), charged=self._charged, credits_left=self._left)


def test_warnings_let_the_run_finish_when_credits_run_low():
    # Acceptance (Problem alerts): warnings let the run finish: credits running low,
    # with the threshold a setting.
    agreed = approval().model_copy(update={"budget_left": 500})
    _, warnings = fetch(Paying(charged=18, left=80), approvals=[agreed], low_credits=100)
    assert warnings.alerts() == [
        Alert(
            code=AlertCode.CREDITS_LOW,
            message="JobsPipe credits running low: 80 left (alerts.low_credits is 100).",
        )
    ]
    _, enough = fetch(Paying(charged=18, left=80), approvals=[agreed], low_credits=50)
    assert enough.alerts() == []


def test_warnings_let_the_run_finish_when_the_credit_budget_is_reached():
    # Acceptance (Problem alerts): warnings let the run finish: credit budget reached.
    agreed = approval().model_copy(update={"budget_left": 18})
    _, warnings = fetch(Paying(charged=18, left=800), approvals=[agreed])
    assert warnings.alerts() == [
        Alert(
            code=AlertCode.BUDGET_REACHED,
            message="JobsPipe monthly budget reached: this run used 18 credits, "
            "and the budget had 18 left this month.",
        )
    ]


def test_low_credits_is_a_setting_of_100_by_default():
    assert SettingsFile.defaults().alerts.low_credits == 100
    assert SettingsFile.defaults(alerts={"low_credits": 500}).alerts.low_credits == 500


class FailingPlan(Planned):
    """A paid source whose cost check fails."""

    def plan(self, criteria, window):
        raise BoardError("HTTP 503 after 3 retries")


def test_a_paid_source_whose_cost_check_fails_is_left_out_and_warned_about():
    prompter = FakePrompter()
    [failed] = CostCheck([FailingPlan(plan())], CRITERIA, prompter).check(RunWindows(window=WINDOW))
    assert (failed.decision, failed.failure) == (SpendDecision.FAILED, "HTTP 503 after 3 retries")
    assert prompter.told == [
        "JobsPipe: the cost check failed (HTTP 503 after 3 retries), so it is left out of this run."
    ]
    source = FailingPlan(plan())
    pages, warnings = fetch(source, Board("getro", "Fast Forward"), approvals=[failed])
    assert source.caps == [] and [page.source for page in pages] == ["getro"]
    assert warnings.messages() == [
        "JobsPipe failed: HTTP 503 after 3 retries (at the cost check). "
        "Its postings are not in this run."
    ]


class Unranked:
    """A ranker that couldn't score some jobs."""

    def __init__(self, scored: int):
        self._scored = scored

    def score(self, jobs, profile):
        return [Recommendation(job=j, score=50, reason="r") for j in jobs[: self._scored]]


def test_warnings_let_the_run_finish_when_the_llm_failed_on_some_postings():
    # Acceptance (Problem alerts): warnings let the run finish: LLM failed on some postings.
    warnings = MemoryWarningLog()
    profile = CandidateProfile(cv="", preferences="")
    step = RecommendTopJobsStep(Unranked(2), profile, 10, 40, guard(), warnings)
    assert len(step.run([job("1"), job("2"), job("3")])) == 2
    assert warnings.alerts() == [
        Alert(
            code=AlertCode.LLM_FAILED,
            message="The LLM couldn't rank 1 of 3 jobs: they can't be recommended.",
        )
    ]


def test_jobs_carried_over_at_the_usage_limit_are_a_warning():
    warnings = MemoryWarningLog()
    limit = UsageLimitGuard(FakePrompter("f"), MemoryPendingLog(), warnings)

    def limited(jobs):
        raise UsageLimitReached([], jobs[1:])

    limit.run(limited, [job("1"), job("2"), job("3")], "labelled")
    assert warnings.alerts() == [
        Alert(
            code=AlertCode.LLM_PENDING,
            message="Usage limit reached: 2 jobs not labelled, carried over to the next run.",
        )
    ]


class Judge:
    """A CV judge that fails with a set error."""

    def __init__(self, error: Exception):
        self._error = error

    def judge(self, asked, profile):
        raise self._error


class NoCache:
    """A gap cache that keeps nothing."""

    def judged(self, cv):
        return {}

    def add(self, cv, judged):
        pass


@pytest.mark.parametrize(
    ("error", "why"),
    [
        (LlmError("down"), "the LLM gave no usable answer"),
        (UsageLimit("limit"), "the LLM's usage limit is reached"),
    ],
)
def test_a_cv_comparison_that_couldnt_be_made_is_a_warning(error, why):
    warnings = MemoryWarningLog()
    builder = GapBuilder(RequirementNames(), 5)
    profile = CandidateProfile(cv="Python", preferences="")
    gaps = CvGaps(profile, Judge(error), NoCache(), builder, warnings)
    rows = tuple(
        AskRow(
            type=RequirementType.SKILL, name=name, jobs=1, share=0.5, change=None, job_ids=("1",)
        )
        for name in ("Python", "SQL")
    )
    asks = Asks(window=WINDOW, previous=WINDOW, jobs=2, previous_jobs=0, rows=rows, low_sample=10)
    gaps.gaps(asks)
    assert warnings.alerts() == [
        Alert(
            code=AlertCode.GAPS_SKIPPED,
            message=f"Experience to gain: 2 requirements weren't compared with your CV ({why}). "
            "The next run asks again.",
        )
    ]


def test_warnings_let_the_run_finish_when_no_new_postings_matched():
    # Acceptance (Problem alerts): warnings let the run finish: no new postings after filtering.
    warnings = MemoryWarningLog()
    report_step(KeepingRenderer(), warnings=warnings).run([])
    assert warnings.alerts() == [
        Alert(code=AlertCode.NO_NEW_JOBS, message="No new jobs matched your searches.")
    ]


def test_the_runs_warnings_are_the_reports_alerts_and_the_terminals():
    # Acceptance (Problem alerts): anything that goes wrong is reported in the terminal
    # and at the top of the report.
    warnings = MemoryWarningLog()
    warnings.warn(AlertCode.SOURCE_EMPTY, "JobsPipe returned no postings.")
    renderer = KeepingRenderer()
    [report] = report_step(renderer, jobs=[job("1")], warnings=warnings).run([])
    assert renderer.content.alerts == (
        Alert(code=AlertCode.SOURCE_EMPTY, message="JobsPipe returned no postings."),
    )
    assert report.summary == "1 new opening, 0 recommended, 1 alert"
    assert report.alerts == ("JobsPipe returned no postings.",)


def test_the_warning_log_keeps_each_warning_once_in_the_run_folder(tmp_path):
    log = FileWarningLog(tmp_path)
    assert log.alerts() == []
    log.warn(AlertCode.SOURCE_EMPTY, "JobsPipe returned no postings.")
    log.warn(AlertCode.LLM_FAILED, "The LLM couldn't rank 1 of 3 jobs.")
    log.warn(AlertCode.SOURCE_EMPTY, "JobsPipe returned no postings.")
    assert [alert.code for alert in FileWarningLog(tmp_path).alerts()] == [
        AlertCode.SOURCE_EMPTY,
        AlertCode.LLM_FAILED,
    ]
    assert len((tmp_path / "warnings.jsonl").read_text().splitlines()) == 2


def test_outside_a_run_warnings_are_told_in_the_terminal_once():
    prompter = FakePrompter()
    terminal = TerminalWarnings(prompter)
    terminal.warn(AlertCode.RUN_UNREADABLE, "Run x can't be read.")
    terminal.warn(AlertCode.RUN_UNREADABLE, "Run x can't be read.")
    assert prompter.told == ["Warning: Run x can't be read."]


def completed_run(runs, name: str) -> None:
    """A completed run folder that kept one job."""
    folder = runs / name
    folder.mkdir(parents=True)
    checkpoints = FileCheckpoints(folder, WINDOW, keep={"extract": FileSeenJobs.FILE})
    checkpoints.save("extract", [job("1")])
    checkpoints.complete()


def test_a_run_folder_that_cant_be_read_is_left_out_with_a_warning(tmp_path):
    completed_run(tmp_path, "2026-11-01T09-00-00")
    completed_run(tmp_path, "2026-11-02T09-00-00")
    (tmp_path / "2026-11-02T09-00-00" / "manifest.json").write_text('{"version": 1}')
    warnings = MemoryWarningLog()
    runs = FileRunHistory(tmp_path, warnings).runs()
    assert [run.id for run in runs] == ["2026-11-01T09-00-00"]
    [alert] = warnings.alerts()
    assert alert.code is AlertCode.RUN_UNREADABLE
    assert alert.message.startswith(
        "Run 2026-11-02T09-00-00 can't be read, so it is left out: its manifest.json is not "
        "as expected (version: "
    )
    assert alert.message.endswith("`job-radar delete` removes it.")


def test_kept_jobs_that_cant_be_read_count_as_none_with_a_warning(tmp_path):
    completed_run(tmp_path, "2026-11-01T09-00-00")
    (tmp_path / "2026-11-01T09-00-00" / "jobs.jsonl").write_text("not json\n")
    warnings = MemoryWarningLog()
    seen = FileSeenJobs(FileRunHistory(tmp_path, warnings), tmp_path, warnings)
    assert seen.keys(date(2026, 11, 9)) == frozenset()
    [alert] = warnings.alerts()
    assert alert.code is AlertCode.KEPT_JOBS_UNREADABLE
    assert alert.message.startswith(
        "The jobs run 2026-11-01T09-00-00 kept can't be read, so they count as new again and "
        "are left out of the market sections: its jobs.jsonl is not as expected ("
    )


def demo_cli(tmp_path, prompter: FakePrompter, hour: int = 10) -> Cli:
    """The real command over demo runs in a temp folder."""
    settings = SettingsFile.defaults(output=str(tmp_path), recommend={"top_n": 3})
    return Cli(
        AppFactory(settings, tmp_path / "config_local", EXAMPLE, FixedClock(hour), prompter, {})
    )


def test_a_demo_run_shows_its_warnings_in_the_report_and_the_terminal(
    tmp_path, capsys, monkeypatch
):
    real_score = KeywordRanker.score
    monkeypatch.setattr(
        KeywordRanker, "score", lambda self, jobs, profile: real_score(self, jobs[1:], profile)
    )
    assert demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"]) == 0
    folder = tmp_path / "demo" / FIRST_RUN
    said = "The LLM couldn't rank 1 of 5 jobs: they can't be recommended."
    assert capsys.readouterr().out == (
        f"Run finished: 5 new openings, 3 recommended, 1 alert.\n- {said}\n"
        f"Report: {folder / 'report.md'}\n"
    )
    report = (folder / "report.md").read_text()
    assert f"## Alerts\n\n- {said}\n\n## Recommended jobs" in report
    assert "alerts: 1\n" in report
    kept = [json.loads(line) for line in (folder / "warnings.jsonl").read_text().splitlines()]
    assert kept == [{"code": "llm_failed", "message": said}]


def test_an_unreadable_earlier_run_is_told_before_the_run_and_recorded_in_it(tmp_path, capsys):
    broken = tmp_path / "demo" / "2026-11-01T09-00-00"
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{")
    prompter = FakePrompter(True)
    assert demo_cli(tmp_path, prompter).main(["run", "--demo"]) == 0
    assert prompter.told[0].startswith("Warning: Run 2026-11-01T09-00-00 can't be read")
    alerts = FileWarningLog(tmp_path / "demo" / FIRST_RUN).alerts()
    assert [alert.code for alert in alerts] == [AlertCode.RUN_UNREADABLE]
    assert "- Run 2026-11-01T09-00-00 can't be read" in capsys.readouterr().out


def test_a_demo_run_with_its_only_board_down_fails_with_no_source(tmp_path, capsys, monkeypatch):
    def down(self, criteria, window):
        raise BoardError("HTTP 503 after 3 retries")

    monkeypatch.setattr(DemoSource, "fetch", down)
    assert demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"]) == 1
    out = capsys.readouterr().out
    assert out.startswith(
        "Run failed at step 'fetch': No source returned data: "
        "Demo board failed (HTTP 503 after 3 retries)\n"
    )
    assert "error.log" not in out
    assert not (tmp_path / "demo" / FIRST_RUN / "error.log").exists()
