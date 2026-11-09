"""The `runs` and `delete` commands: looking at and clearing out earlier runs."""

from job_radar.history import RunFolders, RunHistory
from job_radar.model import RunSummary
from job_radar.prompter import Prompter
from job_radar.words import Words


class RunsCommand:
    """Lists earlier runs, and deletes them after the user confirms.

    Deleting asks first and defaults to no, so a script or a stray Enter
    deletes nothing. Stateless: holds only the run history, the run folders,
    the prompter and how dates are put into words.
    """

    def __init__(
        self, history: RunHistory, folders: RunFolders, prompter: Prompter, words: Words
    ) -> None:
        """Keep where runs are read and deleted, who to ask, and how dates are said."""
        self._history = history
        self._folders = folders
        self._prompter = prompter
        self._words = words

    def show(self) -> int:
        """Tell the user every run, newest first, one per line. The exit code."""
        runs = self._history.runs()
        if not runs:
            self._prompter.tell("No runs yet.")
        for run in runs:
            self._prompter.tell(self.line(run))
        return 0

    def delete(self, run_ids: list[str], every: bool = False) -> int:
        """Delete these runs, or all of them, once the user says yes. The exit code."""
        runs = self._history.runs()
        known = {run.id: run for run in runs}
        unknown = [run_id for run_id in run_ids if run_id not in known]
        if unknown:
            self._prompter.tell(f"No such run: {', '.join(unknown)}. See `job-radar runs`.")
            return 1
        targets = runs if every else [known[run_id] for run_id in dict.fromkeys(run_ids)]
        if not targets:
            self._prompter.tell("No runs to delete." if every else "Name a run, or use --all.")
            return 0 if every else 1
        if not self._prompter.confirm(self._question(targets, every), default=False):
            self._prompter.tell("Nothing was deleted.")
            return 0
        for run in targets:
            self._folders.delete(run.id)
        self._prompter.tell(f"Deleted {self._count(len(targets))}.")
        return 0

    def line(self, run: RunSummary) -> str:
        """One run: id, status, window, and what it found or where it stopped."""
        status = "completed" if run.completed else "failed"
        return f"{run.id}  {status:<9}  {self._words.span(run.window.start, run.window.end)}  " + (
            self._found(run) if run.completed else self._stopped(run)
        )

    def _question(self, targets: list[RunSummary], every: bool) -> str:
        """What to ask before deleting: the run itself, or how many."""
        if len(targets) == 1:
            run = targets[0]
            status = "completed" if run.completed else "failed"
            span = self._words.span(run.window.start, run.window.end)
            return f"Delete run {run.id} ({status}, {span})?"
        return f"Delete {'all ' if every else ''}{len(targets)} runs?"

    @staticmethod
    def _found(run: RunSummary) -> str:
        """How many jobs a completed run recommended."""
        counts = {count.step: count.count for count in run.steps}
        return f"{counts['recommend']} recommended" if "recommend" in counts else ""

    @staticmethod
    def _stopped(run: RunSummary) -> str:
        """The last step a failed run finished."""
        return f"stopped after {run.steps[-1].step}" if run.steps else "stopped before any step"

    @staticmethod
    def _count(n: int) -> str:
        """A number of runs in words: "1 run", "3 runs"."""
        return f"{n} run" if n == 1 else f"{n} runs"
