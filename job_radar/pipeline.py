"""The pipeline: runs the steps of one run in order, so a failed run can be resumed."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from job_radar.checkpoints import Checkpoints
from job_radar.model import Report
from job_radar.result import RunFailed, RunResult, RunSucceeded


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
    `RunFailed` and the final report into `RunSucceeded`, and deletes the
    checkpoints on success. Stateless: a run's progress lives in its checkpoints.
    """

    def __init__(self, steps: Sequence[Step], checkpoints: Checkpoints) -> None:
        """Keep the steps in order and where their outputs are saved."""
        self._steps = steps
        self._checkpoints = checkpoints

    def run(self) -> RunResult:
        """Run every step not done yet and return how the run ended."""
        # TODO(task 4): skip the steps already saved; load the last saved output.
        data: list = []
        for step in self._steps:
            try:
                data = step.run(data)
                self._checkpoints.save(step.name, data)
            except Exception as error:
                return RunFailed(step=step.name, reason=str(error) or type(error).__name__)
        match data:
            case [Report() as report]:
                self._checkpoints.discard_all()
                return RunSucceeded(location=report.location, summary=report.summary)
            case _:
                last = self._steps[-1].name if self._steps else "none"
                return RunFailed(step=last, reason="the last step gave no report")
