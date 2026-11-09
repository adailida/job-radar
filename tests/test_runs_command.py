from datetime import date

from fakes import FakePrompter

from job_radar.model import RunSummary, StepCount, Window
from job_radar.runs_command import RunsCommand
from job_radar.words import Words

WINDOW = Window(start=date(2026, 10, 26), end=date(2026, 11, 9))
DONE = RunSummary(
    id="2026-11-09T14-52-11",
    window=WINDOW,
    completed=True,
    steps=(StepCount(step="filter", count=10), StepCount(step="recommend", count=5)),
)
FAILED = RunSummary(
    id="2026-11-09T14-46-55",
    window=WINDOW,
    completed=False,
    steps=(StepCount(step="fetch", count=2), StepCount(step="filter", count=10)),
)
EMPTY = RunSummary(id="2026-11-09T14-40-00", window=WINDOW, completed=False, steps=())


class ListedRuns:
    """Run history with set runs, newest first."""

    def __init__(self, *runs: RunSummary):
        self._runs = list(runs)

    def last_window(self):
        return None

    def runs(self) -> list[RunSummary]:
        return self._runs


class KeptDeletes:
    """Run folders that remember what they were told to delete."""

    def __init__(self):
        self.deleted: list[str] = []

    def delete(self, run_id: str) -> None:
        self.deleted.append(run_id)


def command(*runs: RunSummary, answers=()) -> tuple[RunsCommand, FakePrompter, KeptDeletes]:
    """The command over these runs, with a user who gives these answers."""
    prompter, folders = FakePrompter(*answers), KeptDeletes()
    return RunsCommand(ListedRuns(*runs), folders, prompter, Words()), prompter, folders


def test_show_lists_each_run_with_what_it_found_or_where_it_stopped():
    runs, prompter, _ = command(DONE, FAILED, EMPTY)
    assert runs.show() == 0
    assert prompter.told == [
        "2026-11-09T14-52-11  completed  26 Oct to 9 Nov 2026  5 recommended",
        "2026-11-09T14-46-55  failed     26 Oct to 9 Nov 2026  stopped after filter",
        "2026-11-09T14-40-00  failed     26 Oct to 9 Nov 2026  stopped before any step",
    ]


def test_show_says_when_there_are_no_runs():
    runs, prompter, _ = command()
    runs.show()
    assert prompter.told == ["No runs yet."]


def test_delete_asks_about_the_run_then_deletes_it():
    runs, prompter, folders = command(DONE, FAILED, answers=[True])
    assert runs.delete([FAILED.id]) == 0
    assert prompter.asked == [f"Delete run {FAILED.id} (failed, 26 Oct to 9 Nov 2026)?"]
    assert folders.deleted == [FAILED.id]
    assert prompter.told == ["Deleted 1 run."]


def test_saying_no_deletes_nothing():
    runs, prompter, folders = command(DONE, answers=[False])
    assert runs.delete([DONE.id]) == 0
    assert folders.deleted == []
    assert prompter.told == ["Nothing was deleted."]


def test_delete_all_asks_once_for_every_run():
    runs, prompter, folders = command(DONE, FAILED, answers=[True])
    assert runs.delete([], every=True) == 0
    assert prompter.asked == ["Delete all 2 runs?"]
    assert folders.deleted == [DONE.id, FAILED.id]


def test_an_unknown_run_deletes_nothing_and_fails():
    runs, prompter, folders = command(DONE)
    assert runs.delete([DONE.id, "2026-01-01T00-00-00"]) == 1
    assert (prompter.asked, folders.deleted) == ([], [])
    assert prompter.told == ["No such run: 2026-01-01T00-00-00. See `job-radar runs`."]


def test_delete_needs_a_run_or_all():
    runs, prompter, _ = command(DONE)
    assert runs.delete([]) == 1
    assert prompter.told == ["Name a run, or use --all."]


def test_delete_all_with_no_runs_says_so():
    runs, prompter, _ = command()
    assert runs.delete([], every=True) == 0
    assert prompter.told == ["No runs to delete."]


def test_delete_all_of_one_run_names_it():
    runs, prompter, _ = command(DONE, answers=[False])
    runs.delete([], every=True)
    assert prompter.asked == [f"Delete run {DONE.id} (completed, 26 Oct to 9 Nov 2026)?"]
