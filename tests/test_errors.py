import os

import pytest
from fakes import WINDOW, FakePrompter, FakeStep, FixedClock, NoCost

from job_radar.app.app_factory import AppFactory
from job_radar.app.job_radar_app import JobRadarApp
from job_radar.app.window import WindowPlan, WindowReason
from job_radar.cli import Cli
from job_radar.config.settings import SettingsFile
from job_radar.config.yaml_file import ConfigError
from job_radar.llm.llm import ClaudeCli, LlmUnavailable
from job_radar.pipeline.pipeline import Pipeline
from job_radar.storage.checkpoints import FileCheckpoints
from job_radar.storage.error_log import FileErrorLog
from job_radar.storage.run_lock import FileRunLock, RunInProgress
from job_radar.utils.errors import JobRadarError

DEAD = 999_999  # a process id taken as no longer running


def lock(folder, pid: int = 4312, alive=lambda pid: pid != DEAD) -> FileRunLock:
    """A run lock for a process with this id, where only `DEAD` isn't running."""
    return FileRunLock(folder, pid=pid, alive=alive)


def test_the_lock_holds_the_process_id_while_the_run_goes_and_is_released_after(tmp_path):
    with lock(tmp_path):
        assert (tmp_path / "run.lock").read_text() == "4312\n"
    assert not (tmp_path / "run.lock").exists()


def test_the_lock_is_released_when_the_run_fails(tmp_path):
    with pytest.raises(RuntimeError), lock(tmp_path):
        raise RuntimeError("bug")
    assert not (tmp_path / "run.lock").exists()


def test_a_live_lock_stops_a_second_run(tmp_path):
    with lock(tmp_path), pytest.raises(RunInProgress) as blocked, lock(tmp_path, pid=5000):
        pass
    assert str(blocked.value).startswith("Another run is in progress (pid 4312). Wait for it")
    assert not (tmp_path / "run.lock").exists()


def test_a_lock_left_by_a_process_that_no_longer_exists_is_removed(tmp_path):
    (tmp_path / "run.lock").write_text(f"{DEAD}\n")
    with lock(tmp_path):
        assert (tmp_path / "run.lock").read_text() == "4312\n"


def test_a_lock_file_that_cant_be_read_counts_as_stale(tmp_path):
    (tmp_path / "run.lock").write_text("not a pid")
    with lock(tmp_path):
        assert (tmp_path / "run.lock").read_text() == "4312\n"


def test_a_lock_another_process_took_over_is_not_removed(tmp_path):
    taken = lock(tmp_path)
    taken.__enter__()
    (tmp_path / "run.lock").write_text("5000\n")
    taken.__exit__(None, None, None)
    assert (tmp_path / "run.lock").read_text() == "5000\n"


def test_this_process_is_running_and_a_finished_one_is_not():
    assert FileRunLock.process_exists(os.getpid())
    assert not FileRunLock.process_exists(DEAD)


def demo_cli(tmp_path, prompter: FakePrompter) -> Cli:
    """The real command over demo runs in a temp folder."""
    settings = SettingsFile.defaults(output=str(tmp_path))
    return Cli(AppFactory(settings, tmp_path / "config_local", FixedClock(), prompter, {}))


def test_a_run_takes_the_lock_and_releases_it_when_it_ends(tmp_path):
    assert demo_cli(tmp_path, FakePrompter(True)).main(["run", "--demo"]) == 0
    assert not (tmp_path / "run.lock").exists()


def test_a_run_while_another_is_in_progress_stops_with_exit_2(tmp_path, capsys):
    (tmp_path / "run.lock").write_text(f"{os.getpid()}\n")
    prompter = FakePrompter()
    assert demo_cli(tmp_path, prompter).main(["run", "--demo"]) == 2
    assert capsys.readouterr().out.startswith(
        f"Could not start the run: Another run is in progress (pid {os.getpid()})."
    )
    assert prompter.asked == [] and not (tmp_path / "demo").exists()
    assert (tmp_path / "run.lock").exists()


class Factory:
    """Builds an app from set parts, or fails to, and says where unexpected errors go."""

    def __init__(self, folder, create_error=None, run_error=None):
        self._folder, self._create_error, self._run_error = folder, create_error, run_error

    def create(self, demo: bool = False) -> JobRadarApp:
        if self._create_error:
            raise self._create_error
        pipeline = Pipeline(
            [FakeStep("fetch", error=self._run_error)],
            FileCheckpoints(self._folder / "run", WINDOW),
            FileErrorLog(self._folder / "run"),
        )
        return JobRadarApp(Offer(), Window(self._run_error), NoCost(), lambda *a: pipeline, Lock())

    def error_log(self) -> FileErrorLog:
        return FileErrorLog(self._folder)


class Offer:
    def offer(self):
        return None


class Window:
    """Agrees the window, or fails as a bug outside any step would."""

    def __init__(self, error):
        self._error = error

    def choose(self):
        if isinstance(self._error, KeyboardInterrupt | TypeError):
            raise self._error
        return WindowPlan(window=WINDOW, reason=WindowReason.FIRST_RUN)


class Lock:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_an_unexpected_error_in_a_step_writes_error_log_in_the_run_folder(tmp_path, capsys):
    (tmp_path / "run").mkdir()
    factory = Factory(tmp_path, run_error=KeyError("results"))
    assert Cli(factory).main(["run"]) == 1
    out = capsys.readouterr().out
    log = tmp_path / "run" / "error.log"
    assert out.splitlines()[:2] == [
        "Run failed at step 'fetch': KeyError: 'results'",
        f"Unexpected error: details in {log}",
    ]
    assert "Traceback" in log.read_text() and "KeyError: 'results'" in log.read_text()


def test_an_unexpected_error_before_any_run_folder_goes_to_the_output_folder(tmp_path, capsys):
    assert Cli(Factory(tmp_path, run_error=TypeError("bug"))).main(["run"]) == 1
    log = tmp_path / "error.log"
    assert capsys.readouterr().out == (
        f"Run stopped: unexpected error (TypeError: bug). Details in {log}\n"
    )
    assert "Traceback" in log.read_text()


def test_an_unexpected_error_while_setting_up_exits_2_with_one_line(tmp_path, capsys):
    assert Cli(Factory(tmp_path, create_error=ValueError("oops"))).main(["run"]) == 2
    log = tmp_path / "error.log"
    assert capsys.readouterr().out == (
        f"Could not set up the run: unexpected error (ValueError: oops). Details in {log}\n"
    )


def test_ctrl_c_stops_with_one_line_and_exit_1(tmp_path, capsys):
    assert Cli(Factory(tmp_path, run_error=KeyboardInterrupt())).main(["run"]) == 1
    assert "Stopped by you." in capsys.readouterr().out


def test_an_expected_error_says_its_message_without_a_type():
    assert JobRadarError.describe(ConfigError("x.yaml: bad\n  key")) == "x.yaml: bad key"
    assert JobRadarError.describe(KeyError()) == "KeyError"


def test_errors_stop_the_run_with_a_clear_message_for_invalid_settings(
    tmp_path, capsys, monkeypatch
):
    # Acceptance (Problem alerts): errors stop the run with a clear message: invalid settings.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config_local").mkdir()
    (tmp_path / "config_local" / "settings.yaml").write_text("recommend:\n  min_scor: 30\n")
    assert Cli.start() == 2
    assert capsys.readouterr().out == (
        "Could not set up the run: config_local/settings.yaml: recommend.min_scor: unknown key. "
        "Fix it in config_local/settings.yaml; config/settings.yaml lists every setting "
        "with its default\n"
    )


def test_errors_stop_the_run_with_a_clear_message_for_invalid_user_input(tmp_path, capsys):
    # Acceptance (Problem alerts): errors stop the run with a clear message: user input
    # missing or invalid.
    local = tmp_path / "config_local"
    local.mkdir()
    (local / "profile.yaml").write_text("searches:\n  one:\n    rols: [engineer]\n")
    factory = AppFactory(
        SettingsFile.defaults(output=str(tmp_path)), local, FixedClock(), FakePrompter(), {}
    )
    assert Cli(factory).main(["run"]) == 2
    assert capsys.readouterr().out == (
        f"Could not set up the run: {local / 'profile.yaml'}: searches.one.rols: unknown key. "
        f"Fix it in {local / 'profile.yaml'}; config/profile.example.yaml shows every key\n"
    )


def test_an_unreadable_cv_names_the_file_and_the_fix(tmp_path, capsys):
    local = tmp_path / "config_local"
    local.mkdir()
    (local / "profile.yaml").write_text("searches:\n  one:\n    roles: [engineer]\n")
    (local / "cv.md").write_text("   \n")
    factory = AppFactory(
        SettingsFile.defaults(output=str(tmp_path)), local, FixedClock(), FakePrompter(), {}
    )
    assert Cli(factory).main(["run"]) == 2
    assert capsys.readouterr().out == f"Could not set up the run: {local / 'cv.md'} has no text\n"


def test_a_missing_api_key_names_the_key_and_the_fix(tmp_path):
    settings = SettingsFile.defaults(output=str(tmp_path), sources={"jobspipe": {"enabled": True}})
    factory = AppFactory(settings, tmp_path, FixedClock(), FakePrompter(), {})
    with pytest.raises(ConfigError) as missing:
        factory._jobspipe()
    assert str(missing.value) == (
        "JOBSPIPE_API_KEY is not set: add it to config_local/.env, "
        "or set sources.jobspipe.enabled: false in config_local/settings.yaml"
    )


@pytest.mark.parametrize(
    ("run", "said"),
    [
        ("missing", "`claude` is not installed: install Claude Code"),
        ("logged out", "`claude` is not logged in: run `claude auth login`"),
    ],
)
def test_errors_stop_the_run_with_a_clear_message_when_the_llm_is_not_available(run, said):
    # Acceptance (Problem alerts): errors stop the run with a clear message: LLM not available.
    import subprocess

    def command(args, **kwargs):
        if run == "missing":
            raise FileNotFoundError("claude")
        return subprocess.CompletedProcess(args, 0, stdout='{"loggedIn": false}', stderr="")

    with pytest.raises(LlmUnavailable) as unavailable:
        ClaudeCli("haiku", run=command).check()
    assert str(unavailable.value) == said
