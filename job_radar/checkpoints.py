"""Where a run's step outputs are kept, so a failed run can be resumed."""

import json
import os
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

    MANIFEST = "manifest.json"
    SCHEMA = 1  # bumped when the saved models change shape

    def __init__(self, folder: Path) -> None:
        """Keep the run folder this run's files go in."""
        self._folder = folder

    def has(self, step: str) -> bool:
        """Whether the manifest lists this step as finished."""
        return any(count.step == step for count in self.funnel())

    def save(self, step: str, items: Sequence[Model]) -> None:
        """Write the step's items to its file and add its count to the manifest.

        The manifest is updated last, so a step counts as finished only once
        its file is complete.
        """
        lines = "".join(item.model_dump_json() + "\n" for item in items)
        self._write(self._step_file(step), lines)
        funnel = [count for count in self.funnel() if count.step != step]
        funnel.append(StepCount(step=step, count=len(items)))
        manifest = {"schema": self.SCHEMA, "steps": [c.model_dump() for c in funnel]}
        self._write(self._folder / self.MANIFEST, json.dumps(manifest, indent=2) + "\n")

    def load[M: Model](self, step: str, kind: type[M]) -> list[M]:
        """Read the step's file back, one item per line."""
        with self._step_file(step).open(encoding="utf-8") as lines:
            return [kind.model_validate_json(line) for line in lines]

    def discard_all(self) -> None:
        """Delete every step file; the manifest and the report stay."""
        for count in self.funnel():
            self._step_file(count.step).unlink(missing_ok=True)

    def funnel(self) -> list[StepCount]:
        """Every finished step and its count, from the manifest."""
        path = self._folder / self.MANIFEST
        if not path.exists():
            return []
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return [StepCount.model_validate(count) for count in manifest["steps"]]

    def _step_file(self, step: str) -> Path:
        """The file a step's output is saved in."""
        return self._folder / f"{step}.jsonl"

    def _write(self, path: Path, text: str) -> None:
        """Write a whole file, so a crash never leaves half of one behind."""
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
