"""Step 10: find what each matched job asks for."""

from job_radar.extract import Extractor
from job_radar.model import Job
from job_radar.prompter import Prompter
from job_radar.usage import UsageLimitGuard


class ExtractStep:
    """Finds the requirements of every matched job: skills, tools, certifications, years.

    Runs after the match step, so only jobs that passed every filter are read.
    A job the extractor couldn't read passes through without requirements, and
    the user is told how many. When the usage limit stops it, the guard settles
    it: the jobs it didn't reach are carried over and leave this run.
    Stateless: holds only the extractor, who it tells and the guard.
    """

    name = "extract"
    output = Job

    def __init__(self, extractor: Extractor, prompter: Prompter, guard: UsageLimitGuard) -> None:
        """Keep the extractor, who to tell about jobs it couldn't read, and the guard."""
        self._extractor = extractor
        self._prompter = prompter
        self._guard = guard

    def run(self, data: list[Job]) -> list[Job]:
        """The jobs in order, each with its requirements if found, minus any carried over."""
        if not data:
            return []
        found, left = self._guard.run(self._extractor.extract, data, "read")
        carried = {job.id for job in left}
        kept = [job for job in data if job.id not in carried]
        failed = sum(1 for job in kept if job.id not in found)
        if failed:
            self._prompter.tell(
                f"The LLM couldn't read the requirements of {failed} of {len(kept)} jobs."
            )
        return [job.model_copy(update={"extraction": found.get(job.id)}) for job in kept]
