"""Ways to score jobs against what the user wants."""

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
        # TODO(task 7): build prompts, check the JSON answers, retry once.
        raise NotImplementedError
