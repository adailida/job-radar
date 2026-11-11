from datetime import date

import pytest
from fakes import MemoryWarningLog, job

from job_radar.models import Window
from job_radar.storage.checkpoints import FileCheckpoints
from job_radar.storage.run_history import FileRunHistory, RunFolders


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
    assert FileRunHistory(tmp_path / "runs", MemoryWarningLog()).last_window() is None


def test_last_window_is_from_the_newest_completed_run(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    run(tmp_path, "2026-11-03T09-00-00", 3, completed=True)
    run(tmp_path, "2026-11-02T09-00-00", 2, completed=True)
    assert FileRunHistory(tmp_path, MemoryWarningLog()).last_window() == window(3)


def test_failed_run_doesnt_count_toward_the_next_window(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    run(tmp_path, "2026-11-03T09-00-00", 3, completed=False)
    assert FileRunHistory(tmp_path, MemoryWarningLog()).last_window() == window(1)


def test_unreadable_and_empty_run_folders_are_skipped(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    old = tmp_path / "2026-11-02T09-00-00"
    old.mkdir()
    (old / "manifest.json").write_text('{"schema": 1, "steps": []}')
    (tmp_path / "2026-11-03T09-00-00").mkdir()
    assert FileRunHistory(tmp_path, MemoryWarningLog()).last_window() == window(1)


def test_runs_lists_completed_and_failed_newest_first(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    run(tmp_path, "2026-11-03T09-00-00", 3, completed=False)
    (tmp_path / "2026-11-04T09-00-00").mkdir()
    runs = FileRunHistory(tmp_path, MemoryWarningLog()).runs()
    assert [(r.id, r.completed, r.window.end.day) for r in runs] == [
        ("2026-11-03T09-00-00", False, 3),
        ("2026-11-01T09-00-00", True, 1),
    ]
    assert [count.step for count in runs[0].steps] == ["dedupe"]


def test_no_runs_folder_means_no_runs(tmp_path):
    assert FileRunHistory(tmp_path / "runs", MemoryWarningLog()).runs() == []


def test_run_folders_delete_one_run_and_nothing_else(tmp_path):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    run(tmp_path, "2026-11-03T09-00-00", 3, completed=True)
    RunFolders(tmp_path).delete("2026-11-01T09-00-00")
    assert [p.name for p in tmp_path.iterdir()] == ["2026-11-03T09-00-00"]


@pytest.mark.parametrize("run_id", ["2026-11-09T00-00-00", "..", "", "../x", "."])
def test_run_folders_refuse_anything_but_an_existing_run(tmp_path, run_id):
    run(tmp_path, "2026-11-01T09-00-00", 1, completed=True)
    with pytest.raises(KeyError):
        RunFolders(tmp_path).delete(run_id)
    assert [p.name for p in tmp_path.iterdir()] == ["2026-11-01T09-00-00"]


def test_runs_carry_the_days_a_long_break_left_out(tmp_path):
    gap = Window(start=date(2026, 10, 1), end=date(2026, 10, 21))
    folder = tmp_path / "2026-11-05T09-00-00"
    folder.mkdir()
    FileCheckpoints(folder, window(5), gap).save("dedupe", [job("1")])
    assert FileRunHistory(tmp_path, MemoryWarningLog()).runs()[0].not_covered == gap
