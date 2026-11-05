import json

from fakes import FakeStep, FixedClock

from job_radar.app import JobRadarApp
from job_radar.checkpoints import FileCheckpoints
from job_radar.cli import Cli
from job_radar.factory import AppFactory, Settings
from job_radar.pipeline import Pipeline
from job_radar.result import RunFailed, RunSucceeded

RUN_FOLDER = "2026-11-05T10-00-00"


def demo_cli(tmp_path) -> Cli:
    """The real command, with run folders in a temp folder and a fixed clock."""
    return Cli(AppFactory(Settings(output=tmp_path, top_n=3), FixedClock()))


class FailingFactory:
    """Builds an app whose only step fails."""

    def __init__(self, folder):
        self._folder = folder

    def create(self, demo: bool = False) -> JobRadarApp:
        step = FakeStep("fetch", error=RuntimeError("board down"))
        return JobRadarApp(Pipeline([step], FileCheckpoints(self._folder)))


class BrokenFactory:
    """Fails to build the app, as with a missing CV."""

    def create(self, demo: bool = False) -> JobRadarApp:
        raise FileNotFoundError("local/cv.pdf not found")


def test_demo_run_end_to_end(tmp_path, capsys):
    assert demo_cli(tmp_path).main(["run", "--demo"]) == 0
    folder = tmp_path / "runs" / RUN_FOLDER
    out = capsys.readouterr().out
    assert out == f"Run finished: 3 jobs recommended.\nReport: {folder / 'report.md'}\n"
    assert sorted(p.name for p in folder.iterdir()) == ["manifest.json", "report.md"]
    report = (folder / "report.md").read_text()
    assert "## Recommended jobs (3)" in report
    assert "1. **Senior Data Engineer**, Brightwater Trust (score 100)" in report
    assert "- convert: 12" in report


def test_new_source_plugs_in_without_changes_downstream(tmp_path):
    # The demo board is added like any board: its own module, wired in the factory only.
    demo_cli(tmp_path).main(["run", "--demo"])
    manifest = json.loads((tmp_path / "runs" / RUN_FOLDER / "manifest.json").read_text())
    counts = {step["step"]: step["count"] for step in manifest["steps"]}
    assert counts == {
        "fetch": 2,
        "convert": 12,
        "dedupe": 12,
        "filter": 12,
        "recommend": 3,
        "report": 1,
    }


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
    assert (succeeded.exit_code(), failed.exit_code()) == (0, 1)
