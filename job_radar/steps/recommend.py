"""Step 9: recommend the jobs that fit the user best."""

from job_radar.model import CandidateProfile, Job, Recommendation
from job_radar.ranking import JobRanker


class RecommendTopJobsStep:
    """Keeps the N jobs that fit the user's CV and preferences best, above a minimum score.

    How jobs are scored is up to the ranker. Stateless: holds only its ranker,
    the profile, N and the minimum score.
    """

    name = "recommend"
    output = Recommendation

    def __init__(
        self, ranker: JobRanker, profile: CandidateProfile, top_n: int, min_score: int
    ) -> None:
        """Keep the ranker, what it ranks against, how many jobs to keep and the lowest score."""
        self._ranker = ranker
        self._profile = profile
        self._top_n = top_n
        self._min_score = min_score

    def run(self, data: list[Job]) -> list[Recommendation]:
        """Score every job and keep the best N that reach the minimum, best first.

        Ties keep the order of the jobs.
        """
        scored = [
            rec for rec in self._ranker.score(data, self._profile) if rec.score >= self._min_score
        ]
        return sorted(scored, key=lambda rec: rec.score, reverse=True)[: self._top_n]
