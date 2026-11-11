"""Step 12: recommend the jobs that fit the user best."""

from job_radar.llm.job_ranker import JobRanker
from job_radar.llm.usage_limit_guard import UsageLimitGuard
from job_radar.models import AlertCode, CandidateProfile, Job, Recommendation
from job_radar.storage.warning_log import WarningLog


class RecommendTopJobsStep:
    """Keeps the N jobs that fit the user's CV and preferences best, above a minimum score.

    How jobs are scored is up to the ranker. A job the ranker couldn't score
    can't be recommended, and it is a warning. When the usage limit stops it,
    the guard settles it: the jobs it didn't reach are carried over.
    Stateless: holds only its ranker, the profile, N, the minimum score, the
    guard and where warnings go.
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
        warnings: WarningLog,
    ) -> None:
        """Keep the ranker, what it ranks against, how many to keep, the lowest score, the logs."""
        self._ranker = ranker
        self._profile = profile
        self._top_n = top_n
        self._min_score = min_score
        self._guard = guard
        self._warnings = warnings

    def run(self, data: list[Job]) -> list[Recommendation]:
        """Score every job and keep the best N that reach the minimum, best first.

        Ties keep the order of the jobs.
        """
        if not data:
            return []
        scored, left = self._guard.run(
            lambda jobs: self._ranker.score(jobs, self._profile), data, "ranked"
        )
        reached = len(data) - len(left)
        failed = reached - len(scored)
        if failed:
            self._warnings.warn(
                AlertCode.LLM_FAILED,
                f"The LLM couldn't rank {failed} of {reached} jobs: they can't be recommended.",
            )
        scored = [rec for rec in scored if rec.score >= self._min_score]
        return sorted(scored, key=lambda rec: rec.score, reverse=True)[: self._top_n]
