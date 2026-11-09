import json

from fakes import WINDOW, FakePrompter, FakeStep, FixedClock

from job_radar.app import JobRadarApp
from job_radar.checkpoints import FileCheckpoints
from job_radar.cli import Cli
from job_radar.factory import AppFactory
from job_radar.pipeline import Pipeline
from job_radar.result import RunCancelled, RunFailed, RunSucceeded
from job_radar.settings import RecommendSettings, Settings

FIRST_RUN = "2026-11-05T10-00-00"


def demo_cli(tmp_path, prompter: FakePrompter, hour: int = 10) -> Cli:
    """The real command, with run folders in a temp folder, a fixed clock and a set user."""
    settings = Settings(output=tmp_path, recommend=RecommendSettings(top_n=3))
    return Cli(AppFactory(settings, tmp_path / "local", FixedClock(hour), prompter))


class FailingFactory:
    """Builds an app whose only step fails."""

    def __init__(self, folder):
        self._folder = folder

    def create(self, demo: bool = False) -> JobRadarApp:
        step = FakeStep("fetch", error=RuntimeError("board down"))
        pipeline = Pipeline([step], FileCheckpoints(self._folder, WINDOW))
        return JobRadarApp(FixedWindow(), lambda window: pipeline)


class FixedWindow:
    """Agrees the same window every time, without asking."""

    def choose(self):
        return WINDOW


class BrokenFactory:
    """Fails to build the app, as with a missing CV."""

    def create(self, demo: bool = False) -> JobRadarApp:
        raise FileNotFoundError("local/cv.pdf not found")


def test_demo_run_end_to_end(tmp_path, capsys):
    prompter = FakePrompter(True)
    assert demo_cli(tmp_path, prompter).main(["run", "--demo"]) == 0
    folder = tmp_path / "demo" / FIRST_RUN
    out = capsys.readouterr().out
    assert out == f"Run finished: 3 jobs recommended.\nReport: {folder / 'report.md'}\n"
    assert prompter.asked == ["Continue?"]
    assert sorted(p.name for p in folder.iterdir()) == ["dropped.md", "manifest.json", "report.md"]
    report = (folder / "report.md").read_text()
    assert "## Recommended jobs (3)" in report
    assert "1. **Senior Data Engineer**, Brightwater Trust (score 100)" in report
    assert "Covers postings from 22 Oct to 5 Nov 2026." in report
    assert "- convert: 12" in report


def test_each_run_writes_one_report_and_saves_its_run_data(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    demo_cli(tmp_path, FakePrompter(), hour=15).main(["run", "--demo"])
    folders = sorted((tmp_path / "demo").iterdir())
    assert [f.name for f in folders] == [FIRST_RUN, "2026-11-05T15-00-00"]
    for folder in folders:
        assert sorted(p.name for p in folder.iterdir()) == [
            "dropped.md",
            "manifest.json",
            "report.md",
        ]
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
        "filter": 8,
        "describe": 8,
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
    assert (counts["convert"], counts["filter"]) == (12, 3)


def test_saying_no_runs_nothing(tmp_path, capsys):
    assert demo_cli(tmp_path, FakePrompter(False)).main(["run", "--demo"]) == 0
    assert capsys.readouterr().out == "Cancelled. Nothing was fetched.\n"
    assert not (tmp_path / "demo").exists()


def test_demo_runs_dont_move_the_real_window(tmp_path):
    demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"])
    assert not (tmp_path / "runs").exists()


def test_failed_run_exits_1_and_says_where(tmp_path, capsys):
    assert Cli(FailingFactory(tmp_path)).main(["run"]) == 1
    assert "Run failed at step 'fetch': board down" in capsys.readouterr().out


def test_setup_error_exits_2(capsys):
    assert Cli(BrokenFactory()).main(["run"]) == 2
    assert "Could not set up the run: local/cv.pdf not found" in capsys.readouterr().out


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
