"""Offering to resume the last run when it failed."""

from job_radar.history import RunHistory
from job_radar.model import RunSummary
from job_radar.prompter import Prompter
from job_radar.words import Words


class ResumeOffer:
    """Asks whether to resume the newest run, when that run didn't complete.

    Only the newest run is offered: an older failed run has been followed by
    another run since. Saying no leaves the failed run where it is; it never
    counts toward the next window. Stateless: holds only the run history, the
    prompter and how dates are put into words.
    """

    def __init__(self, history: RunHistory, prompter: Prompter, words: Words) -> None:
        """Keep where runs are read, who to ask, and how dates are said."""
        self._history = history
        self._prompter = prompter
        self._words = words

    def offer(self) -> RunSummary | None:
        """The failed run to resume, if there is one and the user says yes; else None."""
        runs = self._history.runs()
        if not runs or runs[0].completed:
            return None
        run = runs[0]
        stopped = f"stopped after {run.steps[-1].step}" if run.steps else "stopped before any step"
        span = self._words.span(run.window.start, run.window.end)
        question = f"The last run, {run.id} ({span}), {stopped}. Resume it?"
        return run if self._prompter.confirm(question) else None
