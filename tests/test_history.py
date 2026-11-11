import json
from datetime import date

import pytest
from fakes import MemoryWarningLog, job

from job_radar.models import SourceWindow, Window
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


def sourced_run(runs, name: str, end_day: int, covered: dict[str, bool], completed=True) -> None:
    """A run folder whose sources each had the run's window, covered or not."""
    folder = runs / name
    folder.mkdir(parents=True)
    sources = [SourceWindow(source=source, window=window(end_day)) for source in covered]
    checkpoints = FileCheckpoints(folder, window(end_day), sources=sources)
    checkpoints.record(covered)
    checkpoints.save("fetch", [])
    if completed:
        checkpoints.complete()


def test_a_source_counts_as_covered_only_by_the_runs_that_covered_it(tmp_path):
    # Covered in full by the Nov 1 run; failed, skipped or empty though counted on Nov 3.
    sourced_run(tmp_path, "2026-11-01T09-00-00", 1, {"getro": True, "jobspipe": True})
    sourced_run(tmp_path, "2026-11-03T09-00-00", 3, {"getro": True, "jobspipe": False})
    history = FileRunHistory(tmp_path, MemoryWarningLog())
    assert history.last_covered("getro") == window(3)
    assert history.last_covered("jobspipe") == window(1)
    assert history.last_window() == window(3)


def test_a_source_never_covered_has_no_last_window(tmp_path):
    sourced_run(tmp_path, "2026-11-01T09-00-00", 1, {"getro": True, "jobspipe": False})
    history = FileRunHistory(tmp_path, MemoryWarningLog())
    assert history.last_covered("jobspipe") is None
    assert history.last_covered("demo") is None  # not a source of that run


def test_a_failed_run_covers_no_source(tmp_path):
    sourced_run(tmp_path, "2026-11-01T09-00-00", 1, {"getro": True})
    sourced_run(tmp_path, "2026-11-03T09-00-00", 3, {"getro": True}, completed=False)
    assert FileRunHistory(tmp_path, MemoryWarningLog()).last_covered("getro") == window(1)


def old_manifest(runs, name: str, config: dict | None) -> None:
    """A completed run folder with a version 2 manifest, as written before sources had dates."""
    folder = runs / name
    folder.mkdir(parents=True)
    manifest = {
        "version": 2,
        "window": {"start": "2026-10-28", "end": "2026-11-11"},
        "not_covered": None,
        "config": config,
        "completed": True,
        "steps": [{"step": "fetch", "count": 5}],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))


def test_an_older_run_covered_its_window_for_every_source_it_lists(tmp_path):
    old_manifest(
        tmp_path, "2026-11-11T10-11-33", {"searches": [], "sources": ["getro", "jobspipe"]}
    )
    history = FileRunHistory(tmp_path, MemoryWarningLog())
    whole = Window(start=date(2026, 10, 28), end=date(2026, 11, 11))
    assert history.last_covered("getro") == history.last_covered("jobspipe") == whole
    assert history.last_covered("demo") is None


def test_an_older_run_listing_no_sources_covered_every_source(tmp_path):
    old_manifest(tmp_path, "2026-11-11T10-11-33", None)
    whole = Window(start=date(2026, 10, 28), end=date(2026, 11, 11))
    assert FileRunHistory(tmp_path, MemoryWarningLog()).last_covered("jobspipe") == whole


def test_deleting_a_run_drops_its_coverage(tmp_path):
    sourced_run(tmp_path, "2026-11-01T09-00-00", 1, {"getro": True, "jobspipe": True})
    sourced_run(tmp_path, "2026-11-03T09-00-00", 3, {"getro": True, "jobspipe": True})
    RunFolders(tmp_path).delete("2026-11-03T09-00-00")
    history = FileRunHistory(tmp_path, MemoryWarningLog())
    assert history.last_covered("getro") == history.last_covered("jobspipe") == window(1)
