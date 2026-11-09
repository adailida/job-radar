"""Step 4: keep only jobs no earlier run found."""

from datetime import date

from job_radar.model import Job
from job_radar.seen import SeenJobs


class NewJobsFilterStep:
    """Drops jobs an earlier completed run already found, so a run shows only new ones.

    A job is seen when any of its keys is among the seen keys. With `new_only`
    off, every job passes. Stateless: holds only the seen jobs, the run's day
    and the setting.
    """

    name = "new_jobs_filter"
    output = Job

    def __init__(self, seen: SeenJobs, today: date, new_only: bool) -> None:
        """Keep where seen jobs are read, the run's day, and whether to drop them."""
        self._seen = seen
        self._today = today
        self._new_only = new_only

    def run(self, data: list[Job]) -> list[Job]:
        """The jobs none of whose keys an earlier run found, in order."""
        if not self._new_only:
            return data
        seen = self._seen.keys(self._today)
        return [job for job in data if seen.isdisjoint(job.keys)]
