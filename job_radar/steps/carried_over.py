"""Step 6: add the jobs the last run carried over when it hit the LLM's usage limit."""

from job_radar.model import Job
from job_radar.usage import PendingJobs


class CarriedOverStep:
    """Adds the jobs the last completed run carried over, after the jobs this run's filter kept.

    They come after the filter because they passed it in their own run and are
    usually dated before this run's window, which the filter would drop. They
    skip the seen check, since no run finished them, and cost nothing: they
    come with their descriptions. A carried-over job this run found again (it
    shares a key with one of this run's jobs) is left out, so it isn't twice.
    Stateless: holds only where carried-over jobs are read.
    """

    name = "carried_over"
    output = Job

    def __init__(self, pending: PendingJobs) -> None:
        """Keep where the last run's carried-over jobs are read."""
        self._pending = pending

    def run(self, data: list[Job]) -> list[Job]:
        """This run's jobs, then the carried-over ones it didn't find again."""
        keys = {key for job in data for key in job.keys}
        carried = [job for job in self._pending.jobs() if keys.isdisjoint(job.keys)]
        return [*data, *carried]
