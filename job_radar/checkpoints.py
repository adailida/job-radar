"""Where a run's step outputs are kept, so a failed run can be resumed."""

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from job_radar.model import Model, StepCount, Window


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

    def complete(self) -> None:
        """Mark the run completed and delete every saved output; the counts stay."""
        ...


@runtime_checkable
class RunStats(Protocol):
    """Read-only view of a run's progress: how much each finished step produced."""

    def funnel(self) -> list[StepCount]:
        """Every finished step and its item count, in the order they ran."""
        ...


class Manifest(Model):
    """What a run folder says about its run: its window, its steps, whether it completed."""

    version: Literal[2] = 2  # changed when the saved models change shape
    window: Window
    completed: bool = False
    steps: tuple[StepCount, ...] = ()  # each finished step and its count, in order


class FileCheckpoints:
    """Keeps one run's step outputs as files in the run's folder.

    One JSON Lines file per step, numbered in the order the steps ran
    (`01-fetch.jsonl`, `02-convert.jsonl`), plus `manifest.json` with the run's
    window, each finished step and its count, and whether the run completed.
    Holds only its folder and the run's window; the files are the state.
    """

    MANIFEST = "manifest.json"

    def __init__(self, folder: Path, window: Window) -> None:
        """Keep the run folder this run's files go in, and the window the run covers."""
        self._folder = folder
        self._window = window

    def has(self, step: str) -> bool:
        """Whether the manifest lists this step as finished."""
        return any(count.step == step for count in self.funnel())

    def save(self, step: str, items: Sequence[Model]) -> None:
        """Write the step's items to its file and add its count to the manifest.

        A new step goes after the steps already saved; a step saved again keeps
        its place, so its file keeps its number. The manifest is updated last,
        so a step counts as finished only once its file is complete.
        """
        manifest = self._manifest()
        steps = list(manifest.steps)
        names = [count.step for count in steps]
        position = names.index(step) if step in names else len(steps)
        lines = "".join(item.model_dump_json() + "\n" for item in items)
        self._write(self._step_file(position, step), lines)
        count = StepCount(step=step, count=len(items))
        if step in names:
            steps[position] = count
        else:
            steps.append(count)
        self._save_manifest(manifest.model_copy(update={"steps": tuple(steps)}))

    def load[M: Model](self, step: str, kind: type[M]) -> list[M]:
        """Read the step's file back, one item per line."""
        names = [count.step for count in self.funnel()]
        if step not in names:
            raise KeyError(f"no saved output for the {step} step")
        with self._step_file(names.index(step), step).open(encoding="utf-8") as lines:
            return [kind.model_validate_json(line) for line in lines]

    def complete(self) -> None:
        """Mark the run completed in the manifest, then delete every step file.

        The manifest and the report stay.
        """
        manifest = self._manifest()
        self._save_manifest(manifest.model_copy(update={"completed": True}))
        for position, count in enumerate(manifest.steps):
            self._step_file(position, count.step).unlink(missing_ok=True)

    def funnel(self) -> list[StepCount]:
        """Every finished step and its count, from the manifest."""
        return list(self._manifest().steps)

    def _manifest(self) -> Manifest:
        """The manifest as saved, or a new one if no step has finished yet."""
        path = self._folder / self.MANIFEST
        if not path.exists():
            return Manifest(window=self._window)
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: Manifest) -> None:
        """Write the manifest, readable by people."""
        text = json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
        self._write(self._folder / self.MANIFEST, text)

    def _step_file(self, position: int, step: str) -> Path:
        """The file a step's output is saved in, numbered by its place in the run from 01."""
        return self._folder / f"{position + 1:02d}-{step}.jsonl"

    def _write(self, path: Path, text: str) -> None:
        """Write a whole file, so a crash never leaves half of one behind."""
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
