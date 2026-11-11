"""Step 8: hold back jobs over the cap on how many a run sends to the LLM, when the user says so."""

from job_radar.models import AlertCode, Job
from job_radar.storage.pending_log import PendingLog
from job_radar.storage.warning_log import WarningLog
from job_radar.utils.errors import JobRadarError
from job_radar.utils.prompter import Prompter


class CapStopped(JobRadarError):
    """The user chose to stop the run at the LLM cap, before any job went to the LLM."""


class LlmCapStep:
    """A safety cap on how many jobs one run sends to the LLM, checked before the first LLM step.

    Under the cap, every job goes on and nothing is asked. Over it, the user
    chooses: send them all; send only the first ones up to the cap, in the
    order they come, and carry the rest over to the next run, which is a
    warning; or stop, which fails the run here, before any LLM call, so the
    same command resumes it and asks again. Enter means the first ones.
    Stateless: holds only the cap, who it asks, where carried-over jobs go and
    where warnings go.
    """

    name = "llm_cap"
    output = Job

    def __init__(
        self, cap: int, prompter: Prompter, pending: PendingLog, warnings: WarningLog
    ) -> None:
        """Keep the cap, who to ask, where jobs carried over are kept, and where warnings go."""
        self._cap = cap
        self._prompter = prompter
        self._pending = pending
        self._warnings = warnings

    def run(self, data: list[Job]) -> list[Job]:
        """The jobs that go on to the LLM steps: all of them, or the first ones up to the cap."""
        if len(data) <= self._cap:
            return data
        choice = self._prompter.choose(
            f"{len(data)} jobs would go to Claude, over the cap of {self._cap}. "
            f"Send them all, only the first {self._cap}, or stop?",
            {"a": "send them all", "f": f"send the first {self._cap}", "s": "stop"},
            default="f",
        )
        if choice == "a":
            return data
        if choice == "s":
            raise CapStopped(
                f"stopped before sending {len(data)} jobs to Claude, over llm.ask_above_jobs "
                f"({self._cap}); resuming asks again, with any new cap from "
                "config_local/settings.yaml"
            )
        kept, rest = data[: self._cap], data[self._cap :]
        self._pending.add(rest)
        self._warnings.warn(
            AlertCode.LLM_CAPPED,
            f"Over the LLM cap: {len(rest)} of {len(data)} jobs not sent to Claude, carried "
            f"over to the next run (llm.ask_above_jobs is {self._cap}).",
        )
        return kept
