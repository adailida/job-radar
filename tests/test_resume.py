from datetime import date

from fakes import FakePrompter

from job_radar.app import JobRadarApp
from job_radar.model import RunSummary, StepCount, Window
from job_radar.result import RunCancelled
from job_radar.resume import ResumeOffer
from job_radar.window import WindowPlan, WindowReason
from job_radar.words import Words

WINDOW = Window(start=date(2026, 10, 26), end=date(2026, 11, 9))
FAILED = RunSummary(
    id="2026-11-09T14-46-55",
    window=WINDOW,
    completed=False,
    steps=(StepCount(step="fetch", count=2), StepCount(step="filter", count=10)),
)
DONE = FAILED.model_copy(update={"id": "2026-11-08T09-00-00", "completed": True})


class ListedRuns:
    """Run history with set runs, newest first."""

    def __init__(self, *runs: RunSummary):
        self._runs = list(runs)

    def last_window(self):
        return None

    def runs(self) -> list[RunSummary]:
        return self._runs


def offer(*runs: RunSummary, answers=()) -> tuple[ResumeOffer, FakePrompter]:
    """The offer over these runs, with a user who gives these answers."""
    prompter = FakePrompter(*answers)
    return ResumeOffer(ListedRuns(*runs), prompter, Words()), prompter


def test_offers_the_newest_run_when_it_failed():
    resume, prompter = offer(FAILED, DONE, answers=[True])
    assert resume.offer() == FAILED
    assert prompter.asked == [
        "The last run, 2026-11-09T14-46-55 (26 Oct to 9 Nov 2026), stopped after filter. Resume it?"
    ]


def test_saying_no_offers_nothing():
    resume, _ = offer(FAILED, answers=[False])
    assert resume.offer() is None


def test_asks_nothing_when_the_newest_run_completed_or_there_are_none():
    for runs in [(DONE, FAILED), ()]:
        resume, prompter = offer(*runs)
        assert resume.offer() is None
        assert prompter.asked == []


class Offer:
    """A resume offer with a set answer."""

    def __init__(self, run):
        self._run = run

    def offer(self):
        return self._run


class Chooser:
    """A window chooser with a set window, remembering whether it was asked."""

    def __init__(self, window):
        self._window = window
        self.asked = False

    def choose(self):
        self.asked = True
        return self._window


class Built:
    """A pipeline that remembers it ran."""

    def __init__(self):
        self.ran = False

    def run(self):
        self.ran = True
        return RunCancelled()


def test_the_app_resumes_the_offered_run_in_its_folder_with_its_window():
    built, calls, chooser = Built(), [], Chooser(None)
    app = JobRadarApp(
        Offer(FAILED), chooser, lambda w, gap, run_id: calls.append((w, gap, run_id)) or built
    )
    app.run()
    assert calls == [(WINDOW, None, FAILED.id)]
    assert built.ran and not chooser.asked


def test_the_app_starts_a_new_run_when_nothing_is_resumed():
    plan = WindowPlan(window=WINDOW, reason=WindowReason.FIRST_RUN)
    built, calls, chooser = Built(), [], Chooser(plan)
    app = JobRadarApp(
        Offer(None), chooser, lambda w, gap, run_id: calls.append((w, gap, run_id)) or built
    )
    app.run()
    assert calls == [(WINDOW, None, None)] and chooser.asked
