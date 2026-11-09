"""What happens when the LLM's usage limit is reached in the middle of a run."""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.history import RunHistory
from job_radar.llm import LlmError
from job_radar.model import Job
from job_radar.prompter import Prompter


class UsageLimitReached(Exception):
    """The usage limit stopped an LLM pass partway: what it did, and the jobs it didn't reach.

    `done` has the same shape the pass returns when it finishes.
    """

    def __init__(self, done: object, left: list[Job]) -> None:
        """Keep what the pass did before the limit, and the jobs it didn't reach."""
        super().__init__(f"usage limit reached with {len(left)} jobs left")
        self.done = done
        self.left = left


class LimitStopped(LlmError):
    """The user chose to stop the run at the usage limit, to resume it after the reset."""


@runtime_checkable
class PendingLog(Protocol):
    """Keeps the jobs a run carries over to the next one (Repository)."""

    def add(self, jobs: list[Job]) -> None:
        """Add jobs to carry over; a job already there is kept once."""
        ...

    def jobs(self) -> list[Job]:
        """The jobs carried over, in the order added."""
        ...


class FilePendingLog:
    """Keeps a run's carried-over jobs in `pending.jsonl` in its run folder, kept after the run.

    Holds only its folder; the file is the state.
    """

    NAME = "pending.jsonl"

    def __init__(self, folder: Path) -> None:
        """Keep the run folder the file goes in."""
        self._folder = folder

    def add(self, jobs: list[Job]) -> None:
        """Add the jobs, each once by id, after the ones already there."""
        kept = {job.id: job for job in self.jobs()}
        for job in jobs:
            kept.setdefault(job.id, job)
        lines = "".join(job.model_dump_json() + "\n" for job in kept.values())
        (self._folder / self.NAME).write_text(lines, encoding="utf-8")

    def jobs(self) -> list[Job]:
        """The carried-over jobs; none when nothing was carried over."""
        path = self._folder / self.NAME
        if not path.is_file():
            return []
        with path.open(encoding="utf-8") as lines:
            return [Job.model_validate_json(line) for line in lines if line.strip()]


@runtime_checkable
class PendingJobs(Protocol):
    """Read-only view of the jobs the last completed run carried over."""

    def jobs(self) -> list[Job]:
        """Those jobs, in order; none when it carried nothing over."""
        ...


class LastRunPending:
    """Reads the jobs the newest completed run carried over, from its `pending.jsonl`.

    Stateless: holds only the run history and the folder that holds the runs.
    """

    def __init__(self, history: RunHistory, folder: Path) -> None:
        """Keep the run history and the folder that holds one folder per run."""
        self._history = history
        self._folder = folder

    def jobs(self) -> list[Job]:
        """The newest completed run's carried-over jobs."""
        last = next((run for run in self._history.runs() if run.completed), None)
        return FilePendingLog(self._folder / last.id).jobs() if last else []


class UsageLimitGuard:
    """Runs one LLM pass over jobs, and settles what happens if the usage limit stops it.

    The user chooses: finish with what's done and carry the rest over to the
    next run, or stop the run, which fails at this step and can be resumed
    after the limit resets. Enter means finish. The same rule serves every
    step that calls the LLM. Stateless: holds only who it asks and where
    carried-over jobs go.
    """

    def __init__(self, prompter: Prompter, pending: PendingLog) -> None:
        """Keep who to ask and where jobs carried over are kept."""
        self._prompter = prompter
        self._pending = pending

    def run[T](
        self, work: Callable[[list[Job]], T], jobs: list[Job], verb: str
    ) -> tuple[T, list[Job]]:
        """What the pass did, and the jobs carried over (none when the limit didn't hit).

        `verb` says what the pass does to a job, for the question: "ranked".
        """
        try:
            return work(jobs), []
        except UsageLimitReached as limit:
            left = limit.left
            choice = self._prompter.choose(
                f"{len(left)} jobs not {verb}: usage limit reached. "
                "Finish with what's done and carry them over, or stop?",
                {"f": "finish", "s": "stop"},
                default="f",
            )
            if choice == "s":
                raise LimitStopped(
                    "stopped at the usage limit: run the same command after it resets to resume"
                ) from None
            self._pending.add(left)
            return limit.done, left
