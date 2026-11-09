"""Step 5: keep the jobs that match one of the searches."""

from job_radar.drop_log import DropLog
from job_radar.matching import JobMatcher
from job_radar.model import DropList, DroppedJob, Job, SearchCriteria, Window


class FilterStep:
    """Keeps the jobs that match any of the user's searches.

    A job matches a search when it meets every criterion set in it; a
    criterion left empty lets every job through. Also drops jobs posted before
    the run's window, for boards that return everything they have. Hands the
    jobs the searches dropped, with why, to the drop log. Stateless: holds only
    the searches, the window, the matcher and the drop log.
    """

    name = "filter"
    output = Job

    def __init__(
        self, criteria: SearchCriteria, window: Window, matcher: JobMatcher, log: DropLog
    ) -> None:
        """Keep the searches, the run's window, the matcher, and where dropped jobs are listed."""
        self._criteria = criteria
        self._window = window
        self._matcher = matcher
        self._log = log

    def run(self, data: list[Job]) -> list[Job]:
        """Keep the jobs that match; list the ones the searches dropped, with why."""
        kept: list[Job] = []
        dropped: list[DroppedJob] = []
        in_window = [job for job in data if self._in_window(job)]
        for job in in_window:
            misses = [
                (search.name, self._matcher.miss(job, search)) for search in self._criteria.searches
            ]
            if any(miss is None for _, miss in misses):
                kept.append(job)
            else:
                reasons = tuple(f"{name}: {miss}" for name, miss in misses)
                dropped.append(DroppedJob(job=job, reasons=reasons))
        self._log.write(
            DropList(
                window=self._window,
                checked=len(data),
                kept=len(kept),
                before_window=len(data) - len(in_window),
                dropped=tuple(dropped),
            )
        )
        return kept

    def _in_window(self, job: Job) -> bool:
        """Whether the job's newest posting date is in the window. A job with no date is kept."""
        dates = [posting.posted_at for posting in job.postings if posting.posted_at]
        return not dates or max(dates) >= self._window.start
