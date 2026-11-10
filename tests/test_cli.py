import json
from datetime import date

from fakes import WINDOW, FakePrompter, FakeStep, FixedClock, NoCost, NoLock

from job_radar.app import JobRadarApp
from job_radar.checkpoints import FileCheckpoints
from job_radar.cli import Cli
from job_radar.error_log import FileErrorLog
from job_radar.factory import AppFactory
from job_radar.model import Window
from job_radar.pipeline import Pipeline
from job_radar.profile import ProfileError
from job_radar.ranking import KeywordRanker
from job_radar.result import RunCancelled, RunFailed, RunSucceeded
from job_radar.settings import SettingsFile
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.usage import FilePendingLog, UsageLimitReached
from job_radar.window import WindowPlan, WindowReason

FIRST_RUN = "2026-11-05T10-00-00"


def demo_cli(tmp_path, prompter: FakePrompter, hour: int = 10) -> Cli:
    """The real command, with run folders in a temp folder, a fixed clock and a set user."""
    settings = SettingsFile.defaults(output=str(tmp_path), recommend={"top_n": 3})
    return Cli(AppFactory(settings, tmp_path / "local", FixedClock(hour), prompter, {}))


class FailingFactory:
    """Builds an app whose only step fails."""

    def __init__(self, folder):
        self._folder = folder

    def create(self, demo: bool = False) -> JobRadarApp:
        step = FakeStep("fetch", error=RuntimeError("board down"))
        pipeline = Pipeline(
            [step], FileCheckpoints(self._folder, WINDOW), FileErrorLog(self._folder)
        )
        return JobRadarApp(
            NoResume(), FixedWindow(), NoCost(), lambda window, gap, run_id, ok: pipeline, NoLock()
        )


class NoResume:
    """Never offers to resume a run."""

    def offer(self):
        return None


class FixedWindow:
    """Agrees the same window every time, without asking."""

    def choose(self):
        return WindowPlan(window=WINDOW, reason=WindowReason.FIRST_RUN)


class BrokenFactory:
    """Fails to build the app, as with a missing CV."""

    def create(self, demo: bool = False) -> JobRadarApp:
        raise ProfileError("no CV in local/: add one of cv.pdf, cv.md, cv.txt")


KEPT = ["dropped.md", "jobs.jsonl", "manifest.json", "report.md", "source_counts.jsonl"]
SECTIONS = [
    "## Alerts",
    "## Recommended jobs",
    "## New openings",
    "## Market trends",
    "## What employers ask for",
    "## Experience to gain",
    "## About this run",
]


def test_demo_run_end_to_end(tmp_path, capsys):
    prompter = FakePrompter(True)
    assert demo_cli(tmp_path, prompter).main(["run", "--demo"]) == 0
    folder = tmp_path / "demo" / FIRST_RUN
    out = capsys.readouterr().out
    assert out == (
        f"Run finished: 8 new openings, 3 recommended, 0 alerts.\nReport: {folder / 'report.md'}\n"
    )
    assert prompter.asked == ["Continue?"]
    assert sorted(p.name for p in folder.iterdir()) == KEPT
    report = (folder / "report.md").read_text()
    assert "## Recommended jobs (3)" in report
    assert "1. **Senior Data Engineer**, Brightwater Trust (score 100)" in report
    assert "Covers postings from 22 Oct to 5 Nov 2026." in report
    assert "- convert: 12" in report


def test_a_demo_run_has_every_section_in_order(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    headings = [line.split(" (")[0] for line in report.splitlines() if line.startswith("## ")]
    assert headings == SECTIONS
    assert "sources: {demo: 12}\nnew_openings: 8\nrecommended: 3\nalerts: 0\n" in report
    assert "\nSources: Demo board 12 postings.\n" in report
    assert "## Alerts\n\nNone.\n" in report
    assert "## New openings (8)\n\n### engineering (7)\n\n" in report
    assert "### engineering-management (1)\n\n- **Engineering Manager, Data Platform**" in report
    assert (
        "- **Platform Engineer**, Commons Ledger. Remote. Remote, US. $130k to $160k a year. "
        "Posted 5 Nov. Recommended, score 100. "
        "[Demo board](https://example.org/commons-ledger/jobs/4)\n"
    ) in report


def test_new_openings_are_grouped_as_the_settings_say(tmp_path):
    settings = SettingsFile.defaults(output=str(tmp_path), report={"group_by": "both"})
    factory = AppFactory(settings, tmp_path / "local", FixedClock(10), FakePrompter(True), {})
    Cli(factory).main(["run", "--demo"])
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    assert "### engineering (7)\n\n#### Not labelled (7)\n\n- " in report


def test_each_run_writes_one_report_and_saves_its_run_data(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    demo_cli(tmp_path, FakePrompter(), hour=15).main(["run", "--demo"])
    folders = sorted((tmp_path / "demo").iterdir())
    assert [f.name for f in folders] == [FIRST_RUN, "2026-11-05T15-00-00"]
    # The second run found no new job: a warning, kept in warnings.jsonl.
    for folder, warned in zip(folders, ([], ["warnings.jsonl"]), strict=True):
        assert sorted(p.name for p in folder.iterdir()) == sorted(KEPT + warned)
        manifest = json.loads((folder / "manifest.json").read_text())
        assert manifest["completed"] is True
        assert [step["step"] for step in manifest["steps"]][-1] == "report"
        assert f"run: {folder.name}\n" in (folder / "report.md").read_text()


def test_new_source_plugs_in_without_changes_downstream(tmp_path):
    # The demo board is added like any board: its own module, wired in the factory only.
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    manifest = json.loads((tmp_path / "demo" / FIRST_RUN / "manifest.json").read_text())
    counts = {step["step"]: step["count"] for step in manifest["steps"]}
    assert counts == {
        "fetch": 2,
        "convert": 12,
        "dedupe": 12,
        "new_jobs_filter": 12,
        "filter": 8,
        "carried_over": 8,
        "describe": 8,
        "classify": 8,
        "match": 8,
        "extract": 8,
        "recommend": 3,
        "report": 1,
    }


def test_next_run_fetches_since_the_last_one_without_asking(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    later = FakePrompter()
    assert demo_cli(tmp_path, later, hour=15).main(["run", "--demo"]) == 0
    assert later.asked == []
    assert later.told[0].startswith("The last run was on Nov 5. Fetching Nov 4 to Nov 5")
    manifest = json.loads((tmp_path / "demo" / "2026-11-05T15-00-00" / "manifest.json").read_text())
    assert manifest["window"] == {"start": "2026-11-04", "end": "2026-11-05"}
    counts = {step["step"]: step["count"] for step in manifest["steps"]}
    # The first run found 8 of the 12 jobs: only the 4 it didn't keep are new.
    assert (counts["convert"], counts["new_jobs_filter"], counts["filter"]) == (12, 4, 0)


def test_the_report_lists_every_matching_posting_not_seen_in_an_earlier_run(tmp_path, capsys):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    first = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    assert "## New openings (8)" in first
    demo_cli(tmp_path, FakePrompter(), hour=15).main(["run", "--demo"])
    second = (tmp_path / "demo" / "2026-11-05T15-00-00" / "report.md").read_text()
    assert "## New openings (0)\n\nNo new job matched your searches this run.\n" in second
    assert capsys.readouterr().out.endswith(
        "Run finished: 0 new openings, 0 recommended, 1 alert.\n"
        "- No new jobs matched your searches.\n"
        f"Report: {tmp_path / 'demo' / '2026-11-05T15-00-00' / 'report.md'}\n"
    )


def test_saying_no_runs_nothing(tmp_path, capsys):
    assert demo_cli(tmp_path, FakePrompter(False)).main(["run", "--demo"]) == 0
    assert capsys.readouterr().out == "Cancelled. Nothing was fetched.\n"
    assert not (tmp_path / "demo").exists()


def test_demo_runs_dont_move_the_real_window(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    assert not (tmp_path / "runs").exists()


def test_failed_run_exits_1_and_says_where(tmp_path, capsys):
    assert Cli(FailingFactory(tmp_path)).main(["run"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("Run failed at step 'fetch': RuntimeError: board down\n")
    assert f"Unexpected error: details in {tmp_path / 'error.log'}\n" in out
    assert "Traceback" in (tmp_path / "error.log").read_text()


def test_setup_error_exits_2(capsys):
    assert Cli(BrokenFactory()).main(["run"]) == 2
    assert "Could not set up the run: no CV in local/: add one of cv.pdf" in capsys.readouterr().out


def test_no_command_shows_help(capsys):
    assert Cli(BrokenFactory()).main([]) == 0
    assert "run" in capsys.readouterr().out


def test_results_say_how_the_run_ended():
    succeeded = RunSucceeded(location="out/report.md", summary="3 jobs recommended")
    failed = RunFailed(step="fetch", reason="board down")
    assert succeeded.message() == "Run finished: 3 jobs recommended.\nReport: out/report.md"
    assert failed.message().startswith("Run failed at step 'fetch': board down\n")
    assert RunCancelled().message() == "Cancelled. Nothing was fetched."
    assert (succeeded.exit_code(), failed.exit_code(), RunCancelled().exit_code()) == (0, 1, 0)


def test_runs_lists_demo_runs_and_delete_removes_one(tmp_path, capsys):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    capsys.readouterr()
    listing = FakePrompter()
    assert demo_cli(tmp_path, listing).main(["runs", "--demo"]) == 0
    assert listing.told == [f"{FIRST_RUN}  completed  22 Oct to 5 Nov 2026  3 recommended"]
    deleting = FakePrompter(True)
    assert demo_cli(tmp_path, deleting).main(["delete", "--demo", FIRST_RUN]) == 0
    assert list((tmp_path / "demo").iterdir()) == []


def test_a_failed_demo_run_is_resumed_by_the_same_command(tmp_path, capsys, monkeypatch):
    real_run = RecommendTopJobsStep.run

    def broken(self, data):
        raise RuntimeError("ranker down")

    monkeypatch.setattr(RecommendTopJobsStep, "run", broken)
    assert demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"]) == 1
    assert "Run the same command again to resume" in capsys.readouterr().out
    monkeypatch.setattr(RecommendTopJobsStep, "run", real_run)
    again = FakePrompter(True)
    assert demo_cli(tmp_path, again, hour=11).main(["run", "--demo"]) == 0
    assert again.asked == [
        f"The last run, {FIRST_RUN} (22 Oct to 5 Nov 2026), stopped after extract. Resume it?"
    ]
    folders = list((tmp_path / "demo").iterdir())
    assert [f.name for f in folders] == [FIRST_RUN]
    manifest = json.loads((folders[0] / "manifest.json").read_text())
    assert manifest["completed"] is True
    assert "## Recommended jobs (3)" in (folders[0] / "report.md").read_text()


def test_a_run_after_a_long_break_says_in_the_report_which_days_it_missed(tmp_path):
    old = tmp_path / "demo" / "2026-09-30T10-00-00"
    old.mkdir(parents=True)
    checkpoints = FileCheckpoints(old, Window(start=date(2026, 9, 16), end=date(2026, 9, 30)))
    checkpoints.save("report", [])
    checkpoints.complete()
    assert demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"]) == 0
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    assert "Not covered: 1 Oct to 21 Oct 2026. The last run was on 30 Sep" in report


def test_with_new_only_off_a_second_run_sees_every_job_again(tmp_path):
    settings = SettingsFile.defaults(output=str(tmp_path), new_only=False, recommend={"top_n": 3})
    for hour in (10, 15):
        cli = Cli(
            AppFactory(settings, tmp_path / "local", FixedClock(hour), FakePrompter(True), {})
        )
        assert cli.main(["run", "--demo"]) == 0
    manifest = json.loads((tmp_path / "demo" / "2026-11-05T15-00-00" / "manifest.json").read_text())
    counts = {step["step"]: step["count"] for step in manifest["steps"]}
    assert counts["new_jobs_filter"] == 12


def test_jobs_the_usage_limit_stopped_are_ranked_by_the_next_run(tmp_path, monkeypatch):
    real_score = KeywordRanker.score

    def limited(self, jobs, profile):
        raise UsageLimitReached(real_score(self, jobs[:2], profile), jobs[2:])

    monkeypatch.setattr(KeywordRanker, "score", limited)
    first = FakePrompter(True, "f")
    assert demo_cli(tmp_path, first).main(["run", "--demo"]) == 0
    assert first.asked[-1].startswith("6 jobs not ranked: usage limit reached.")
    folder = tmp_path / "demo" / FIRST_RUN
    assert len(FilePendingLog(folder).jobs()) == 6
    assert (
        "6 jobs carried over to the next run (usage limit)." in (folder / "report.md").read_text()
    )
    monkeypatch.setattr(KeywordRanker, "score", real_score)
    assert demo_cli(tmp_path, FakePrompter(), hour=15).main(["run", "--demo"]) == 0
    manifest = json.loads((tmp_path / "demo" / "2026-11-05T15-00-00" / "manifest.json").read_text())
    counts = {step["step"]: step["count"] for step in manifest["steps"]}
    assert (counts["filter"], counts["carried_over"]) == (0, 6)
    assert counts["recommend"] == 3


def test_a_demo_run_reports_market_trends(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    assert "## Market trends (by month)" in report
    assert "| New postings per covered day |" in report
    assert "Nothing to compare yet" in report
    manifest = json.loads((tmp_path / "demo" / FIRST_RUN / "manifest.json").read_text())
    assert manifest["config"]["sources"] == ["demo"]


def test_a_demo_run_reports_what_employers_ask_for(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    section = report.index("## What employers ask for")
    assert report.index("## Market trends") < section < report.index("## About this run")
    assert "In the 30 days from 7 Oct to 5 Nov 2026: 8 matched jobs (low sample)." in report
    assert "### Tools" in report
    assert "| Python | 25% (2) |" in report
    assert "No change yet: no matched job with requirements in the 30 days before." in report


def test_how_many_requirements_the_report_lists_is_a_setting(tmp_path):
    settings = SettingsFile.defaults(output=str(tmp_path), report={"requirements_per_type": 1})
    factory = AppFactory(settings, tmp_path / "local", FixedClock(10), FakePrompter(True), {})
    Cli(factory).main(["run", "--demo"])
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    tools = report[report.index("### Tools") :].split("\n\n")[1]
    assert tools.splitlines() == ["| Requirement | Share |", "|---|---|", "| Python | 25% (2) |"]


def test_a_demo_run_reports_experience_to_gain(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    section = report.index("## Experience to gain")
    assert report.index("## What employers ask for") < section < report.index("## About this run")
    assert (
        "| machine learning | 12% (1) | missing: not named in the CV "
        "| Use it in a small project of your own. |"
    ) in report
    assert "Covered: Python." in report
    assert (tmp_path / "cache" / "demo-gaps.jsonl").is_file()
    assert not (tmp_path / "cache" / "gaps.jsonl").exists()


def test_how_many_gaps_show_how_to_gain_them_is_a_setting(tmp_path):
    settings = SettingsFile.defaults(output=str(tmp_path), report={"gap_suggestions": 0})
    factory = AppFactory(settings, tmp_path / "local", FixedClock(10), FakePrompter(True), {})
    Cli(factory).main(["run", "--demo"])
    report = (tmp_path / "demo" / FIRST_RUN / "report.md").read_text()
    assert "| machine learning | 12% (1) | missing: not named in the CV |  |" in report
