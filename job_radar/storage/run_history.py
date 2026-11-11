"""What earlier runs covered, read from their run folders."""

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from job_radar.models import AlertCode, RunSummary, Window
from job_radar.storage.checkpoints import FileCheckpoints, Manifest
from job_radar.storage.warning_log import WarningLog


@runtime_checkable
class RunHistory(Protocol):
    """Read-only view of earlier runs (Repository). Stateless."""

    def last_window(self) -> Window | None:
        """The window of the last completed run, or None when no run has completed."""
        ...

    def last_covered(self, source: str) -> Window | None:
        """A source's dates in the last completed run that covered it, or None if none did."""
        ...

    def runs(self) -> list[RunSummary]:
        """Every run, completed or not, newest first."""
        ...


class FileRunHistory:
    """Reads earlier runs from the run folders under one parent folder.

    Only completed runs count: a failed run is skipped, and a source counts
    as covered only by the runs that fetched it in full. A folder whose manifest
    can't be read, such as one from an older version, is skipped with a
    warning. Holds only the parent folder and where warnings go; the run
    folders are the state.
    """

    def __init__(self, folder: Path, warnings: WarningLog) -> None:
        """Keep the folder that holds one folder per run, and where warnings go."""
        self._folder = folder
        self._warnings = warnings

    def last_window(self) -> Window | None:
        """The window of the newest completed run."""
        return next((run.window for run in self.runs() if run.completed), None)

    def last_covered(self, source: str) -> Window | None:
        """The source's dates in the newest completed run that covered it in full."""
        return next(
            (window for run in self.runs() if (window := run.covered(source)) is not None), None
        )

    def runs(self) -> list[RunSummary]:
        """Every run folder with a readable manifest, newest first (folders are named by start)."""
        if not self._folder.is_dir():
            return []
        found = []
        for run in sorted(self._folder.iterdir(), reverse=True):
            manifest = self._manifest(run)
            if manifest is not None:
                found.append(
                    RunSummary(
                        id=run.name,
                        window=manifest.window,
                        not_covered=manifest.not_covered,
                        completed=manifest.completed,
                        config=manifest.config,
                        steps=manifest.steps,
                        sources=manifest.sources,
                    )
                )
        return found

    def _manifest(self, run: Path) -> Manifest | None:
        """A run folder's manifest, or None when it has none or it can't be read."""
        path = run / FileCheckpoints.MANIFEST
        if not path.is_file():
            return None
        try:
            return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, OSError, UnicodeDecodeError) as error:
            self._warnings.warn(
                AlertCode.RUN_UNREADABLE,
                f"Run {run.name} can't be read, so it is left out: its {FileCheckpoints.MANIFEST} "
                f"is not as expected ({self.problem(error)}). `job-radar delete` removes it.",
            )
            return None

    @staticmethod
    def problem(error: Exception) -> str:
        """What's wrong with a file of a run, in a few words: the first field at fault."""
        if isinstance(error, ValidationError):
            first = error.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            return f"{where}: {first['msg']}" if where else first["msg"]
        return type(error).__name__


class RunFolders:
    """Deletes run folders under one parent folder.

    Only names an existing run folder directly under the parent, so a typo or
    a path can't reach anything else. Holds only the parent folder; the run
    folders are the state.
    """

    def __init__(self, folder: Path) -> None:
        """Keep the folder that holds one folder per run."""
        self._folder = folder

    def delete(self, run_id: str) -> None:
        """Delete one run's folder and everything in it."""
        target = self._folder / run_id
        if "/" in run_id or run_id in ("", ".", "..") or not target.is_dir():
            raise KeyError(f"no run {run_id!r} in {self._folder}/")
        shutil.rmtree(target)
