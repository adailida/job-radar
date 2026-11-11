"""Where a run's step outputs are kept, so a failed run can be resumed."""

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from job_radar.models import Model, RunConfig, SourceWindow, StepCount, Window


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


@runtime_checkable
class CoverageLog(Protocol):
    """Records which sources a run covered in full, so the next run knows where each starts."""

    def record(self, covered: Mapping[str, bool]) -> None:
        """Record, for each source fetched, whether it was covered in full."""
        ...


class Manifest(Model):
    """What a run folder says about its run: its windows, its steps, whether it completed.

    Version 3 added each source's own dates and whether the run covered
    them; a version 2 manifest has none, and counts as covering its window
    for every source it lists.
    """

    version: Literal[2, 3] = 3  # changed when the saved models change shape
    window: Window  # spans every source's window
    not_covered: Window | None = None  # days a long break left out, before the window
    sources: tuple[SourceWindow, ...] = ()  # each source's dates and coverage; () in version 2
    config: RunConfig | None = None  # what the run searched for and where; None in older runs
    completed: bool = False
    steps: tuple[StepCount, ...] = ()  # each finished step and its count, in order


class FileCheckpoints:
    """Keeps one run's step outputs as files in the run's folder.

    One JSON Lines file per step, numbered in the order the steps ran
    (`01-fetch.jsonl`, `02-convert.jsonl`), plus `manifest.json` with the run's
    windows, which sources it covered, each finished step and its count, and
    whether the run completed. Holds only its folder, the run's windows, the
    days it didn't cover, what to keep and what the run searches for; the
    files are the state.
    """

    MANIFEST = "manifest.json"

    def __init__(
        self,
        folder: Path,
        window: Window,
        not_covered: Window | None = None,
        keep: Mapping[str, str] | None = None,
        config: RunConfig | None = None,
        sources: Sequence[SourceWindow] = (),
    ) -> None:
        """Keep the run folder, its window, the days a long break left out, and what to keep.

        `keep` names steps whose output stays after the run completes, and the
        file it stays as: `{"filter": "jobs.jsonl"}`. `config` is what the run
        searches for and where, and `sources` each source's own dates, both
        recorded in the manifest.
        """
        self._folder = folder
        self._window = window
        self._not_covered = not_covered
        self._keep = dict(keep or {})
        self._config = config
        self._sources = tuple(sources)

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

    def kept[M: Model](self, kind: type[M]) -> list[M]:
        """The output of the first step to keep, whether still a step file or already kept.

        Empty when that step hasn't finished.
        """
        if not self._keep:
            return []
        step, name = next(iter(self._keep.items()))
        path = self._folder / name
        if not path.is_file():
            return self.load(step, kind) if self.has(step) else []
        with path.open(encoding="utf-8") as lines:
            return [kind.model_validate_json(line) for line in lines if line.strip()]

    def complete(self) -> None:
        """Mark the run completed in the manifest, then delete every step file.

        The manifest and the report stay, and so does the output of each step
        to keep, under its kept name.
        """
        manifest = self._manifest()
        for position, count in enumerate(manifest.steps):
            if count.step in self._keep:
                self._step_file(position, count.step).replace(self._folder / self._keep[count.step])
        self._save_manifest(manifest.model_copy(update={"completed": True}))
        for position, count in enumerate(manifest.steps):
            self._step_file(position, count.step).unlink(missing_ok=True)

    def funnel(self) -> list[StepCount]:
        """Every finished step and its count, from the manifest."""
        return list(self._manifest().steps)

    def record(self, covered: Mapping[str, bool]) -> None:
        """Mark each source covered or not in the manifest; a fetch done again replaces it.

        A source without dates of its own, as in a resumed older run, is added
        with the run's window.
        """
        manifest = self._manifest()
        sources = list(manifest.sources)
        names = [source.source for source in sources]
        for name, done in covered.items():
            if name in names:
                position = names.index(name)
                sources[position] = sources[position].model_copy(update={"covered": done})
            else:
                window, gap = manifest.window, manifest.not_covered
                sources.append(
                    SourceWindow(source=name, window=window, not_covered=gap, covered=done)
                )
        self._save_manifest(manifest.model_copy(update={"version": 3, "sources": tuple(sources)}))

    def _manifest(self) -> Manifest:
        """The manifest as saved, or a new one if no step has finished yet."""
        path = self._folder / self.MANIFEST
        if not path.exists():
            return Manifest(
                window=self._window,
                not_covered=self._not_covered,
                sources=self._sources,
                config=self._config,
            )
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
