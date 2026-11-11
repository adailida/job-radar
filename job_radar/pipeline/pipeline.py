"""The pipeline: runs the steps of one run in order, so a failed run can be resumed."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from job_radar.app.run_result import RunFailed, RunResult, RunSucceeded
from job_radar.models import Report
from job_radar.storage.checkpoints import Checkpoints
from job_radar.storage.error_log import ErrorLog
from job_radar.utils.errors import JobRadarError
from job_radar.utils.progress import NoProgress, Progress


@runtime_checkable
class Step[In, Out](Protocol):
    """One step of a run: takes the previous step's output, gives its own.

    `In` and `Out` are the model types it takes and gives. The first step takes
    nothing, so its `In` is `Never` and it gets an empty list. Steps know nothing
    about saving: the pipeline saves every output.
    """

    name: str  # also the name of its saved output
    output: type[Out]  # so a saved output can be read back as the right model

    def run(self, data: list[In]) -> list[Out]:
        """Do this step's work on the previous step's output."""
        ...


class Pipeline:
    """Runs the steps in order and says how the run ended.

    Saves every step's output and passes it to the next step in memory. When
    resuming, skips the steps an earlier attempt saved and loads the last saved
    output from disk, since nothing is in memory yet. Turns an error into
    `RunFailed`, with an unexpected one's traceback in the error log, and the
    final report into `RunSucceeded`, and on success marks the run
    completed, which deletes the checkpoints. Tells the progress reporter
    when each step starts, ends, is skipped or fails. Stateless: a run's
    progress lives in its checkpoints.
    """

    NOUNS = {  # what a step's output is called, singular and plural, by model name
        "RawPage": ("page", "pages"),
        "Posting": ("posting", "postings"),
        "Job": ("job", "jobs"),
        "Recommendation": ("recommendation", "recommendations"),
    }

    def __init__(
        self,
        steps: Sequence[Step],
        checkpoints: Checkpoints,
        errors: ErrorLog,
        progress: Progress | None = None,
    ) -> None:
        """Keep the steps in order, where outputs are saved, where bugs go, who shows progress."""
        self._steps = steps
        self._checkpoints = checkpoints
        self._errors = errors
        self._progress = progress or NoProgress()

    def step_names(self) -> list[str]:
        """The names of the steps, in order."""
        return [step.name for step in self._steps]

    def run(self) -> RunResult:
        """Run every step not done yet and return how the run ended.

        The steps an earlier attempt saved, from the first one on, are skipped;
        the last of them is read back from disk as the next step's input.
        """
        start = 0
        while start < len(self._steps) and self._checkpoints.has(self._steps[start].name):
            start += 1
        total = len(self._steps)
        for number, step in enumerate(self._steps[:start], start=1):
            self._progress.skipped(number, total, step.name)
        data: list = []
        if start:
            last = self._steps[start - 1]
            try:
                data = self._checkpoints.load(last.name, last.output)
            except Exception as error:
                return RunFailed(step=last.name, reason=f"can't read its saved output: {error}")
        for number, step in enumerate(self._steps[start:], start=start + 1):
            self._progress.begin(number, total, step.name)
            try:
                data = step.run(data)
                self._checkpoints.save(step.name, data)
            except Exception as error:
                self._progress.failed()
                return self._failed(step.name, error)
            self._progress.done(self._summary(step, data))
        match data:
            case [Report() as report]:
                self._checkpoints.complete()
                return RunSucceeded(
                    location=report.location, summary=report.summary, alerts=report.alerts
                )
            case _:
                last = self._steps[-1].name if self._steps else "none"
                return RunFailed(step=last, reason="the last step gave no report")

    def _summary(self, step: Step, data: list) -> str:
        """What a finished step gave, for its line: "470 jobs", or "report written"."""
        if step.output is Report:
            return "report written"
        one, many = self.NOUNS.get(step.output.__name__, ("item", "items"))
        return f"{len(data)} {one if len(data) == 1 else many}"

    def _failed(self, step: str, error: Exception) -> RunFailed:
        """The failed run for an error at a step; an unexpected error's details go to the log."""
        reason = JobRadarError.describe(error)
        if isinstance(error, JobRadarError):
            return RunFailed(step=step, reason=reason)
        return RunFailed(step=step, reason=reason, details=self._errors.write(error))
