"""The jobs a run carries over to the next one, and reading them back."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.models import Job
from job_radar.storage.run_history import RunHistory


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
