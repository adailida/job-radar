"""How a run ended: success or failure, each able to describe itself to the user."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class RunResult(ABC):
    """How one run ended: what to tell the user and which exit code to return.

    Immutable. Whoever shows the result calls `message` and `exit_code` without
    checking which kind of result it is, so a new kind needs no change there.
    """

    @abstractmethod
    def message(self) -> str:
        """What to tell the user about the run, in one or two lines."""

    @abstractmethod
    def exit_code(self) -> int:
        """The process exit code for this outcome."""


@dataclass(frozen=True)
class RunSucceeded(RunResult):
    """A run that finished every step: where its report is and what it found."""

    location: str
    summary: str

    def message(self) -> str:
        """Say what the run found and where the report is."""
        return f"Run finished: {self.summary}.\nReport: {self.location}"

    def exit_code(self) -> int:
        """Exit code for a successful run."""
        return 0


@dataclass(frozen=True)
class RunFailed(RunResult):
    """A run that stopped at a step: which step, and why."""

    step: str
    reason: str

    def message(self) -> str:
        """Say which step failed and why, and that the finished steps are kept."""
        # TODO(task 13): say that a rerun resumes after the last finished step.
        return (
            f"Run failed at step '{self.step}': {self.reason}\n"
            "The steps that finished are kept in the run folder."
        )

    def exit_code(self) -> int:
        """Exit code for a failed run."""
        return 1
