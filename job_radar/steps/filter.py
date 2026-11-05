"""Step 4: keep the jobs that match the search."""

from job_radar.model import Job, Search, Window
from job_radar.normalize import Normalizer


class FilterStep:
    """Keeps the jobs that match every criterion set in the search.

    A criterion left empty lets every job through. Also drops jobs posted before
    the run's window, for boards that return everything they have. Stateless:
    holds only the search, the window and the normalizer.
    """

    name = "filter"
    output = Job

    def __init__(self, search: Search, window: Window, normalizer: Normalizer) -> None:
        """Keep the search jobs are checked against, the run's window, and how titles compare."""
        self._search = search
        self._window = window
        self._normalize = normalizer

    def run(self, data: list[Job]) -> list[Job]:
        """Keep the jobs that match."""
        return [job for job in data if self.matches(job)]

    def matches(self, job: Job) -> bool:
        """Whether the job meets every criterion set in the search, and is in the window."""
        # TODO(task 11): locations, work mode, keywords, excluded titles, salary, if_missing.
        return self._in_window(job) and self._has_role(job)

    def _has_role(self, job: Job) -> bool:
        """Whether the title contains one of the search's roles as whole words, any case.

        "data engineer" matches "Senior Data Engineer"; "intern" doesn't match
        "International". With no roles set, every job matches.
        """
        if not self._search.roles:
            return True
        title = f" {self._normalize.title(job.postings[0].title)} "
        return any(f" {self._normalize.title(role)} " in title for role in self._search.roles)

    def _in_window(self, job: Job) -> bool:
        """Whether the job's newest posting date is in the window. A job with no date is kept."""
        dates = [posting.posted_at for posting in job.postings if posting.posted_at]
        return not dates or max(dates) >= self._window.start
