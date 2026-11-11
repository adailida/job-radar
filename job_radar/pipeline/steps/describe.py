"""Step 7: fetch full descriptions for the jobs kept."""

from collections.abc import Mapping

from job_radar.models import Job
from job_radar.sources.base import JobDescriber
from job_radar.utils.prompter import Prompter


class DescribeStep:
    """Fills in the description of each job's primary posting, from the board it came from.

    Runs after the filter, so only jobs worth ranking cost a request. A job
    whose primary posting already has a description, or whose board has no
    describer (it sends descriptions with its postings), passes through as it
    is. Tells the user first how long it will take. Stateless: holds only its
    describers and the prompter.
    """

    name = "describe"
    output = Job

    def __init__(self, describers: Mapping[str, JobDescriber], prompter: Prompter) -> None:
        """Keep one describer per board, by board name, and how to tell the user things."""
        self._describers = describers
        self._prompter = prompter

    def run(self, data: list[Job]) -> list[Job]:
        """Describe every job that needs it, in order; the others pass through."""
        needed = [job for job in data if self._describer(job)]
        if needed:
            self._prompter.tell(self._estimate(needed))
        return [self._described(job) for job in data]

    def _describer(self, job: Job) -> JobDescriber | None:
        """The describer for the job's primary posting, or none when it needs no description."""
        primary = job.postings[0]
        return None if primary.description else self._describers.get(primary.source)

    def _described(self, job: Job) -> Job:
        """The job with its primary posting's description filled in, when it needs one."""
        describer = self._describer(job)
        if describer is None:
            return job
        primary, *others = job.postings
        primary = primary.model_copy(update={"description": describer.describe(primary)})
        return job.model_copy(update={"postings": (primary, *others)})

    def _estimate(self, jobs: list[Job]) -> str:
        """What the step is about to do and roughly how long it takes."""
        seconds = sum(self._describers[job.postings[0].source].pace for job in jobs)
        took = "under a minute" if seconds < 60 else f"about {round(seconds / 60)} min"
        noun = "job" if len(jobs) == 1 else "jobs"
        return f"Fetching full descriptions for {len(jobs)} {noun}: {took}."
