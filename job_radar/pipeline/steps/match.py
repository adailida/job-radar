"""Step 10: keep the jobs that match a search on every criterion, labels included."""

from job_radar.matching.job_matcher import JobMatcher
from job_radar.models import Job, SearchCriteria


class MatchStep:
    """Keeps the jobs that meet every criterion of some search, now that they have labels.

    The filter already checked the posting's own fields; this checks them all
    again with the labels, so seniority and domain count too. Stateless: holds
    only the searches and the matcher.
    """

    name = "match"
    output = Job

    def __init__(self, criteria: SearchCriteria, matcher: JobMatcher) -> None:
        """Keep the searches and the matcher."""
        self._criteria = criteria
        self._matcher = matcher

    def run(self, data: list[Job]) -> list[Job]:
        """The jobs, in order, that match at least one search."""
        return [
            job
            for job in data
            if any(self._matcher.miss(job, search) is None for search in self._criteria.searches)
        ]
