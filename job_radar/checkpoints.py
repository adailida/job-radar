"""Where a run's step outputs are kept, so a failed run can be resumed."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.model import Model, StepCount


@runtime_checkable
class Checkpoints(Protocol):
    """Saves and reads back each step's output for one run (Repository).

    Also records how many items each step produced. Files today; a database
    could implement the same methods later.
    """

    def has(self, step: str) -> bool:
        """Whether this step's output was saved, so the step can be skipped."""
        ...

    def save(self, step: str, items: Sequence[Model]) -> None:
        """Save a step's output and record how many items it had."""
        ...

    def load[M: Model](self, step: str, kind: type[M]) -> list[M]:
        """Read a step's saved output back."""
        ...

    def discard_all(self) -> None:
        """Delete every saved output once the run has succeeded; the counts stay."""
        ...


@runtime_checkable
class RunStats(Protocol):
    """Read-only view of a run's progress: how much each finished step produced."""

    def funnel(self) -> list[StepCount]:
        """Every finished step and its item count, in the order they ran."""
        ...


class FileCheckpoints:
    """Keeps one run's step outputs as files in the run's folder.

    One JSON Lines file per step, plus `manifest.json` with each finished step
    and its count. Holds only its folder; the files are the state.
    """

    def __init__(self, folder: Path) -> None:
        """Keep the run folder this run's files go in."""
        self._folder = folder

    def has(self, step: str) -> bool:
        """Whether the manifest lists this step as finished."""
        # TODO(task 3): read the manifest.
        raise NotImplementedError

    def save(self, step: str, items: Sequence[Model]) -> None:
        """Write the step's items to its file and add its count to the manifest."""
        # TODO(task 3): write JSON Lines and update the manifest.
        raise NotImplementedError

    def load[M: Model](self, step: str, kind: type[M]) -> list[M]:
        """Read the step's file back, one item per line."""
        # TODO(task 3): read JSON Lines.
        raise NotImplementedError

    def discard_all(self) -> None:
        """Delete every step file; the manifest and the report stay."""
        # TODO(task 3): delete the step files.
        raise NotImplementedError

    def funnel(self) -> list[StepCount]:
        """Every finished step and its count, from the manifest."""
        # TODO(task 3): read the manifest.
        raise NotImplementedError
