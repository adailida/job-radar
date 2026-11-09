"""Step 4: keep the jobs that match one of the searches."""

from job_radar.model import Job, Search, SearchCriteria, Window
from job_radar.normalize import Normalizer


class FilterStep:
    """Keeps the jobs that match any of the user's searches.

    A job matches a search when it meets every criterion set in it; a
    criterion left empty lets every job through. Also drops jobs posted before
    the run's window, for boards that return everything they have. Stateless:
    holds only the searches, the window and the normalizer.
    """

    name = "filter"
    output = Job

    def __init__(self, criteria: SearchCriteria, window: Window, normalizer: Normalizer) -> None:
        """Keep the searches jobs are checked against, the run's window, and how titles compare."""
        self._criteria = criteria
        self._window = window
        self._normalize = normalizer

    def run(self, data: list[Job]) -> list[Job]:
        """Keep the jobs that match."""
        return [job for job in data if self.matches(job)]

    def matches(self, job: Job) -> bool:
        """Whether the job is in the window and matches at least one search."""
        # TODO(task 11): locations, work mode, keywords, excluded titles, salary, if_missing.
        return self._in_window(job) and any(
            self._has_role(job, search) for search in self._criteria.searches
        )

    def _has_role(self, job: Job, search: Search) -> bool:
        """Whether the title contains one of the search's roles as whole words, any case.

        "data engineer" matches "Senior Data Engineer"; "intern" doesn't match
        "International". With no roles set, every job matches.
        """
        if not search.roles:
            return True
        title = f" {self._normalize.title(job.postings[0].title)} "
        return any(f" {self._normalize.title(role)} " in title for role in search.roles)

    def _in_window(self, job: Job) -> bool:
        """Whether the job's newest posting date is in the window. A job with no date is kept."""
        dates = [posting.posted_at for posting in job.postings if posting.posted_at]
        return not dates or max(dates) >= self._window.start
