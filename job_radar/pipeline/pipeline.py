"""The pipeline: runs the steps of one run in order, so a failed run can be resumed."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from job_radar.app.run_result import RunFailed, RunResult, RunSucceeded
from job_radar.models import Report
from job_radar.storage.checkpoints import Checkpoints
from job_radar.storage.error_log import ErrorLog
from job_radar.utils.errors import JobRadarError


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
    completed, which deletes the checkpoints. Stateless: a run's progress
    lives in its checkpoints.
    """

    def __init__(self, steps: Sequence[Step], checkpoints: Checkpoints, errors: ErrorLog) -> None:
        """Keep the steps in order, where their outputs are saved, and where bugs are written."""
        self._steps = steps
        self._checkpoints = checkpoints
        self._errors = errors

    def run(self) -> RunResult:
        """Run every step not done yet and return how the run ended.

        The steps an earlier attempt saved, from the first one on, are skipped;
        the last of them is read back from disk as the next step's input.
        """
        start = 0
        while start < len(self._steps) and self._checkpoints.has(self._steps[start].name):
            start += 1
        data: list = []
        if start:
            last = self._steps[start - 1]
            try:
                data = self._checkpoints.load(last.name, last.output)
            except Exception as error:
                return RunFailed(step=last.name, reason=f"can't read its saved output: {error}")
        for step in self._steps[start:]:
            try:
                data = step.run(data)
                self._checkpoints.save(step.name, data)
            except Exception as error:
                return self._failed(step.name, error)
        match data:
            case [Report() as report]:
                self._checkpoints.complete()
                return RunSucceeded(
                    location=report.location, summary=report.summary, alerts=report.alerts
                )
            case _:
                last = self._steps[-1].name if self._steps else "none"
                return RunFailed(step=last, reason="the last step gave no report")

    def _failed(self, step: str, error: Exception) -> RunFailed:
        """The failed run for an error at a step; an unexpected error's details go to the log."""
        reason = JobRadarError.describe(error)
        if isinstance(error, JobRadarError):
            return RunFailed(step=step, reason=reason)
        return RunFailed(step=step, reason=reason, details=self._errors.write(error))
