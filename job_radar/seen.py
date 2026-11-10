"""Jobs that earlier completed runs already found."""

from datetime import date, timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from job_radar.history import FileRunHistory, RunHistory
from job_radar.model import AlertCode, Job
from job_radar.warning_log import WarningLog


@runtime_checkable
class SeenJobs(Protocol):
    """Read-only view of the jobs earlier completed runs passed through their filter."""

    def keys(self, today: date) -> frozenset[str]:
        """Every key that marks a job as seen today."""
        ...

    def jobs(self, run_id: str) -> list[Job]:
        """The jobs one completed run kept; none if it kept none."""
        ...


class FileSeenJobs:
    """Reads the jobs each completed run kept, from `jobs.jsonl` in its run folder.

    A job's strong keys (its ATS key, each posting's own key) mark it as seen
    for good: the employer's id isn't reused. Its fuzzy keys (company, title,
    country) count only for 60 days, so a new opening with an old title still
    shows up later. Deleting a run makes its jobs unseen again. A kept file
    that can't be read counts as none, with a warning. Stateless: holds only
    where runs are and where warnings go.
    """

    FILE = "jobs.jsonl"
    FUZZY_DAYS = 60

    def __init__(self, history: RunHistory, folder: Path, warnings: WarningLog) -> None:
        """Keep the run history, the folder that holds one folder per run, and the warnings."""
        self._history = history
        self._folder = folder
        self._warnings = warnings

    def keys(self, today: date) -> frozenset[str]:
        """The strong keys of every kept job, and the fuzzy keys of those kept recently."""
        found: set[str] = set()
        recent = today - timedelta(days=self.FUZZY_DAYS)
        for run in self._history.runs():
            if not run.completed:
                continue
            fuzzy_counts = run.window.end >= recent
            for job in self.jobs(run.id):
                found.update(key for key in job.keys if fuzzy_counts or not self.is_fuzzy(key))
        return frozenset(found)

    def jobs(self, run_id: str) -> list[Job]:
        """The jobs in one run's kept file; none, with a warning, if it can't be read."""
        path = self._folder / run_id / self.FILE
        if not path.is_file():
            return []
        try:
            with path.open(encoding="utf-8") as lines:
                return [Job.model_validate_json(line) for line in lines if line.strip()]
        except (ValidationError, OSError, UnicodeDecodeError) as error:
            self._warnings.warn(
                AlertCode.KEPT_JOBS_UNREADABLE,
                f"The jobs run {run_id} kept can't be read, so they count as new again and are "
                f"left out of the market sections: its {self.FILE} is not as expected "
                f"({FileRunHistory.problem(error)}).",
            )
            return []

    @staticmethod
    def is_fuzzy(key: str) -> bool:
        """Whether a key is the weaker company, title and country kind."""
        return "|" in key
