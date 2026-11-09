"""Step 7: label each job with its seniority, job type, domain and sector."""

from job_radar.classify import Classifier
from job_radar.model import Job
from job_radar.prompter import Prompter


class ClassifyStep:
    """Labels every job, so the searches' seniority and domain can be checked.

    A job the classifier couldn't label passes through without labels, and the
    user is told how many. Stateless: holds only the classifier and who it tells.
    """

    name = "classify"
    output = Job

    def __init__(self, classifier: Classifier, prompter: Prompter) -> None:
        """Keep the classifier and who to tell about jobs it couldn't label."""
        self._classifier = classifier
        self._prompter = prompter

    def run(self, data: list[Job]) -> list[Job]:
        """The same jobs, in order, each with its labels when it got some."""
        labels = self._classifier.classify(data) if data else {}
        failed = sum(1 for job in data if job.id not in labels)
        if failed:
            self._prompter.tell(f"The LLM couldn't label {failed} of {len(data)} jobs.")
        return [job.model_copy(update={"classification": labels.get(job.id)}) for job in data]
