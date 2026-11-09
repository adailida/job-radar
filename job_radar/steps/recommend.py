"""Step 11: recommend the jobs that fit the user best."""

from job_radar.model import CandidateProfile, Job, Recommendation
from job_radar.ranking import JobRanker
from job_radar.usage import UsageLimitGuard


class RecommendTopJobsStep:
    """Keeps the N jobs that fit the user's CV and preferences best, above a minimum score.

    How jobs are scored is up to the ranker. When the usage limit stops it, the
    guard settles it: the jobs it didn't reach are carried over. Stateless:
    holds only its ranker, the profile, N, the minimum score and the guard.
    """

    name = "recommend"
    output = Recommendation

    def __init__(
        self,
        ranker: JobRanker,
        profile: CandidateProfile,
        top_n: int,
        min_score: int,
        guard: UsageLimitGuard,
    ) -> None:
        """Keep the ranker, what it ranks against, how many to keep, the lowest score, the guard."""
        self._ranker = ranker
        self._profile = profile
        self._top_n = top_n
        self._min_score = min_score
        self._guard = guard

    def run(self, data: list[Job]) -> list[Recommendation]:
        """Score every job and keep the best N that reach the minimum, best first.

        Ties keep the order of the jobs.
        """
        scored, _ = self._guard.run(
            lambda jobs: self._ranker.score(jobs, self._profile), data, "ranked"
        )
        scored = [rec for rec in scored if rec.score >= self._min_score]
        return sorted(scored, key=lambda rec: rec.score, reverse=True)[: self._top_n]
