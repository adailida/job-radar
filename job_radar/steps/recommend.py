"""Step 5: recommend the jobs that fit the user best."""

from job_radar.model import CandidateProfile, Job, Recommendation
from job_radar.ranking import JobRanker


class RecommendTopJobsStep:
    """Keeps the N jobs that fit the user's CV and preferences best.

    How jobs are scored is up to the ranker. Stateless: holds only its ranker,
    the profile and N.
    """

    name = "recommend"
    output = Recommendation

    def __init__(self, ranker: JobRanker, profile: CandidateProfile, top_n: int) -> None:
        """Keep the ranker, what it ranks against, and how many jobs to keep."""
        self._ranker = ranker
        self._profile = profile
        self._top_n = top_n

    def run(self, data: list[Job]) -> list[Recommendation]:
        """Score every job and keep the best N, best first."""
        # TODO(task 7): score, sort, cut.
        raise NotImplementedError
