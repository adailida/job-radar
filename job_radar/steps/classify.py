"""Step 8: label each job with its seniority, job type, domain and sector."""

from job_radar.classify import Classifier
from job_radar.model import AlertCode, Job
from job_radar.prompter import Prompter
from job_radar.usage import UsageLimitGuard
from job_radar.warning_log import WarningLog


class ClassifyStep:
    """Labels every job, so the searches' seniority and domain can be checked.

    A job the classifier couldn't label passes through without labels; the
    user is told how many, and it is a warning. When the usage limit stops
    it, the guard settles it: the jobs it didn't reach are carried over and
    leave this run. Stateless: holds only the classifier, who it tells, the
    guard and where warnings go.
    """

    name = "classify"
    output = Job

    def __init__(
        self,
        classifier: Classifier,
        prompter: Prompter,
        guard: UsageLimitGuard,
        warnings: WarningLog,
    ) -> None:
        """Keep the classifier, who to tell about jobs it couldn't label, the guard, the log."""
        self._classifier = classifier
        self._prompter = prompter
        self._guard = guard
        self._warnings = warnings

    def run(self, data: list[Job]) -> list[Job]:
        """The jobs in order, each with its labels when it got some, minus any carried over."""
        if not data:
            return []
        labels, left = self._guard.run(self._classifier.classify, data, "labelled")
        carried = {job.id for job in left}
        kept = [job for job in data if job.id not in carried]
        failed = sum(1 for job in kept if job.id not in labels)
        if failed:
            message = (
                f"The LLM couldn't label {failed} of {len(kept)} jobs: "
                "their seniority and domain count as not given."
            )
            self._prompter.tell(message)
            self._warnings.warn(AlertCode.LLM_FAILED, message)
        return [job.model_copy(update={"classification": labels.get(job.id)}) for job in kept]
