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
        # TODO(task 3): build the success message.
        raise NotImplementedError

    def exit_code(self) -> int:
        """Exit code for a successful run."""
        # TODO(task 3): return 0.
        raise NotImplementedError


@dataclass(frozen=True)
class RunFailed(RunResult):
    """A run that stopped at a step: which step, and why."""

    step: str
    reason: str

    def message(self) -> str:
        """Say which step failed, why, and that a rerun resumes from there."""
        # TODO(task 3): build the failure message.
        raise NotImplementedError

    def exit_code(self) -> int:
        """Exit code for a failed run."""
        # TODO(task 3): return 1.
        raise NotImplementedError
