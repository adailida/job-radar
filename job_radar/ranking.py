"""Ways to score jobs against what the user wants."""

import re
from typing import Protocol, runtime_checkable

from job_radar.llm import Llm
from job_radar.model import CandidateProfile, Job, Recommendation


@runtime_checkable
class JobRanker(Protocol):
    """Scores jobs against the user's CV and preferences (Strategy). Stateless."""

    def score(self, jobs: list[Job], profile: CandidateProfile) -> list[Recommendation]:
        """Give every job a score and a one-line reason."""
        ...


class LlmRanker:
    """Scores jobs by asking a language model, a batch of jobs at a time.

    Stateless: holds only its model and batch size.
    """

    def __init__(self, llm: Llm, batch_size: int) -> None:
        """Keep the model to ask and how many jobs go in one prompt."""
        self._llm = llm
        self._batch_size = batch_size

    def score(self, jobs: list[Job], profile: CandidateProfile) -> list[Recommendation]:
        """Ask the model to score each batch of jobs against the profile."""
        # TODO(task 7b): build prompts, check the JSON answers, retry once.
        raise NotImplementedError


class KeywordRanker:
    """Scores a job by how many words of its title appear in the CV and preferences.

    Crude but free, offline and predictable: used by `job-radar run --demo` and
    the end-to-end tests in place of a language model. Stateless.
    """

    IGNORED = frozenset({"and", "for", "the", "with"})

    def score(self, jobs: list[Job], profile: CandidateProfile) -> list[Recommendation]:
        """Score each job by the share of its title words found in the profile."""
        known = self._words(f"{profile.cv} {profile.preferences}")
        return [self._recommend(job, known) for job in jobs]

    def _recommend(self, job: Job, known: set[str]) -> Recommendation:
        """Score one job against the profile's words, with the words that matched."""
        title = self._words(job.postings[0].title)
        found = sorted(title & known)
        score = round(100 * len(found) / len(title)) if title else 0
        reason = (
            f"Title words in your profile: {', '.join(found)}"
            if found
            else "No title words in your profile"
        )
        return Recommendation(job=job, score=score, reason=reason)

    def _words(self, text: str) -> set[str]:
        """The distinct lowercase words of a text, leaving out very short and filler words."""
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        return {word for word in words if len(word) > 2 and word not in self.IGNORED}
