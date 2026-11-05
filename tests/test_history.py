from datetime import date

from fakes import job

from job_radar.checkpoints import FileCheckpoints
from job_radar.history import FileRunHistory
from job_radar.model import Window


def window(end_day: int) -> Window:
    return Window(start=date(2026, 10, 22), end=date(2026, 11, end_day))


def run(runs, name: str, end_day: int, completed: bool) -> None:
    """A run folder with one saved step, completed or not."""
    folder = runs / name
    folder.mkdir(parents=True)
    checkpoints = FileCheckpoints(folder, window(end_day))
    checkpoints.save("dedupe", [job("1")])
    if completed:
        checkpoints.complete()


def test_no_runs_folder_means_no_history(tmp_path):
    assert FileRunHistory(tmp_path / "runs").last_window() is None


def test_last_window_is_from_the_newest_completed_run(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    run(tmp_path, "2026-11-03T09-00-00", 3, completed=True)
    run(tmp_path, "2026-11-02T09-00-00", 2, completed=True)
    assert FileRunHistory(tmp_path).last_window() == window(3)


def test_failed_run_doesnt_count_toward_the_next_window(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    run(tmp_path, "2026-11-03T09-00-00", 3, completed=False)
    assert FileRunHistory(tmp_path).last_window() == window(1)


def test_unreadable_and_empty_run_folders_are_skipped(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    old = tmp_path / "2026-11-02T09-00-00"
    old.mkdir()
    (old / "manifest.json").write_text('{"schema": 1, "steps": []}')
    (tmp_path / "2026-11-03T09-00-00").mkdir()
    assert FileRunHistory(tmp_path).last_window() == window(1)
