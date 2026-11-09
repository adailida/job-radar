"""Step 9: find what each matched job asks for."""

from job_radar.extract import Extractor
from job_radar.model import Job
from job_radar.prompter import Prompter


class ExtractStep:
    """Finds the requirements of every matched job: skills, tools, certifications, years.

    Runs after the match step, so only jobs that passed every filter are read.
    A job the extractor couldn't read passes through without requirements, and
    the user is told how many. Stateless: holds only the extractor and who it tells.
    """

    name = "extract"
    output = Job

    def __init__(self, extractor: Extractor, prompter: Prompter) -> None:
        """Keep the extractor and who to tell about jobs it couldn't read."""
        self._extractor = extractor
        self._prompter = prompter

    def run(self, data: list[Job]) -> list[Job]:
        """The same jobs, in order, each with its requirements when it got some."""
        found = self._extractor.extract(data) if data else {}
        failed = sum(1 for job in data if job.id not in found)
        if failed:
            self._prompter.tell(
                f"The LLM couldn't read the requirements of {failed} of {len(data)} jobs."
            )
        return [job.model_copy(update={"extraction": found.get(job.id)}) for job in data]
