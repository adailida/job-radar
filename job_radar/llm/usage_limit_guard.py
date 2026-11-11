"""What happens when the LLM's usage limit is reached in the middle of a run."""

from collections.abc import Callable

from job_radar.llm.llm import LlmError
from job_radar.models import AlertCode, Job
from job_radar.storage.pending_log import PendingLog
from job_radar.storage.warning_log import WarningLog
from job_radar.utils.prompter import Prompter


class UsageLimitReached(Exception):
    """The usage limit stopped an LLM pass partway: what it did, and the jobs it didn't reach.

    `done` has the same shape the pass returns when it finishes.
    """

    def __init__(self, done: object, left: list[Job]) -> None:
        """Keep what the pass did before the limit, and the jobs it didn't reach."""
        super().__init__(f"usage limit reached with {len(left)} jobs left")
        self.done = done
        self.left = left


class LimitStopped(LlmError):
    """The user chose to stop the run at the usage limit, to resume it after the reset."""


class UsageLimitGuard:
    """Runs one LLM pass over jobs, and settles what happens if the usage limit stops it.

    The user chooses: finish with what's done and carry the rest over to the
    next run, which is a warning, or stop the run, which fails at this step
    and can be resumed after the limit resets. Enter means finish. The same
    rule serves every step that calls the LLM. Stateless: holds only who it
    asks, where carried-over jobs go and where warnings go.
    """

    def __init__(self, prompter: Prompter, pending: PendingLog, warnings: WarningLog) -> None:
        """Keep who to ask, where jobs carried over are kept, and where warnings go."""
        self._prompter = prompter
        self._pending = pending
        self._warnings = warnings

    def run[T](
        self, work: Callable[[list[Job]], T], jobs: list[Job], verb: str
    ) -> tuple[T, list[Job]]:
        """What the pass did, and the jobs carried over (none when the limit didn't hit).

        `verb` says what the pass does to a job, for the question: "ranked".
        """
        try:
            return work(jobs), []
        except UsageLimitReached as limit:
            left = limit.left
            choice = self._prompter.choose(
                f"{len(left)} jobs not {verb}: usage limit reached. "
                "Finish with what's done and carry them over, or stop?",
                {"f": "finish", "s": "stop"},
                default="f",
            )
            if choice == "s":
                raise LimitStopped(
                    "stopped at the usage limit: run the same command after it resets to resume"
                ) from None
            self._pending.add(left)
            self._warnings.warn(
                AlertCode.LLM_PENDING,
                f"Usage limit reached: {len(left)} jobs not {verb}, carried over to the next run.",
            )
            return limit.done, left
