"""Jobs that earlier completed runs already found."""

from datetime import date, timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from job_radar.history import RunHistory
from job_radar.model import Job


@runtime_checkable
class SeenJobs(Protocol):
    """Read-only view of the jobs earlier completed runs passed through their filter."""

    def keys(self, today: date) -> frozenset[str]:
        """Every key that marks a job as seen today."""
        ...


class FileSeenJobs:
    """Reads the jobs each completed run kept, from `jobs.jsonl` in its run folder.

    A job's strong keys (its ATS key, each posting's own key) mark it as seen
    for good: the employer's id isn't reused. Its fuzzy keys (company, title,
    country) count only for 60 days, so a new opening with an old title still
    shows up later. Deleting a run makes its jobs unseen again. Stateless:
    holds only where runs are.
    """

    FILE = "jobs.jsonl"
    FUZZY_DAYS = 60

    def __init__(self, history: RunHistory, folder: Path) -> None:
        """Keep the run history and the folder that holds one folder per run."""
        self._history = history
        self._folder = folder

    def keys(self, today: date) -> frozenset[str]:
        """The strong keys of every kept job, and the fuzzy keys of those kept recently."""
        found: set[str] = set()
        recent = today - timedelta(days=self.FUZZY_DAYS)
        for run in self._history.runs():
            if not run.completed:
                continue
            fuzzy_counts = run.window.end >= recent
            for job in self.read(self._folder / run.id / self.FILE):
                found.update(key for key in job.keys if fuzzy_counts or not self.is_fuzzy(key))
        return frozenset(found)

    @staticmethod
    def is_fuzzy(key: str) -> bool:
        """Whether a key is the weaker company, title and country kind."""
        return "|" in key

    @staticmethod
    def read(path: Path) -> list[Job]:
        """The jobs in one run's kept file; none if it has none or it can't be read."""
        if not path.is_file():
            return []
        try:
            with path.open(encoding="utf-8") as lines:
                return [Job.model_validate_json(line) for line in lines if line.strip()]
        except ValidationError:
            # TODO(task 24): warn about kept jobs that can't be read.
            return []
