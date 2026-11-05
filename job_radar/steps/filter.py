"""Step 4: keep the jobs that match the search."""

from job_radar.model import Job, Search


class FilterStep:
    """Keeps the jobs that match every criterion set in the search.

    A criterion left empty lets every job through. Stateless: holds only the search.
    """

    name = "filter"
    output = Job

    def __init__(self, search: Search) -> None:
        """Keep the search jobs are checked against."""
        self._search = search

    def run(self, data: list[Job]) -> list[Job]:
        """Keep the jobs that match."""
        return [job for job in data if self.matches(job)]

    def matches(self, job: Job) -> bool:
        """Whether the job meets every criterion set in the search."""
        # TODO(task 6): check the roles; until then every job matches.
        return True
