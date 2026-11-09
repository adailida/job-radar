"""Step 4: keep the jobs that match one of the searches."""

from job_radar.matching import JobMatcher
from job_radar.model import Job, SearchCriteria, Window


class FilterStep:
    """Keeps the jobs that match any of the user's searches.

    A job matches a search when it meets every criterion set in it; a
    criterion left empty lets every job through. Also drops jobs posted before
    the run's window, for boards that return everything they have. Stateless:
    holds only the searches, the window and the matcher.
    """

    name = "filter"
    output = Job

    def __init__(self, criteria: SearchCriteria, window: Window, matcher: JobMatcher) -> None:
        """Keep the searches jobs are checked against, the run's window, and the matcher."""
        self._criteria = criteria
        self._window = window
        self._matcher = matcher

    def run(self, data: list[Job]) -> list[Job]:
        """Keep the jobs that match."""
        return [job for job in data if self.matches(job)]

    def matches(self, job: Job) -> bool:
        """Whether the job is in the window and matches at least one search."""
        return self._in_window(job) and any(
            self._matcher.miss(job, search) is None for search in self._criteria.searches
        )

    def _in_window(self, job: Job) -> bool:
        """Whether the job's newest posting date is in the window. A job with no date is kept."""
        dates = [posting.posted_at for posting in job.postings if posting.posted_at]
        return not dates or max(dates) >= self._window.start
