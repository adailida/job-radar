"""What earlier runs covered, read from their run folders."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from job_radar.checkpoints import FileCheckpoints, Manifest
from job_radar.model import Window


@runtime_checkable
class RunHistory(Protocol):
    """Read-only view of earlier runs (Repository). Stateless."""

    def last_window(self) -> Window | None:
        """The window of the last completed run, or None when no run has completed."""
        ...


class FileRunHistory:
    """Reads earlier runs from the run folders under one parent folder.

    Only completed runs count: a failed run is skipped. A folder whose manifest
    can't be read, such as one from an older version, is skipped too. Holds
    only the parent folder; the run folders are the state.
    """

    def __init__(self, folder: Path) -> None:
        """Keep the folder that holds one folder per run."""
        self._folder = folder

    def last_window(self) -> Window | None:
        """The window of the newest completed run. Run folders are named by start time."""
        if not self._folder.is_dir():
            return None
        for run in sorted(self._folder.iterdir(), reverse=True):
            manifest = self._manifest(run)
            if manifest is not None and manifest.completed:
                return manifest.window
        return None

    def _manifest(self, run: Path) -> Manifest | None:
        """A run folder's manifest, or None when it has none or it can't be read."""
        path = run / FileCheckpoints.MANIFEST
        if not path.is_file():
            return None
        try:
            return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError:
            # TODO(task 24): warn about run folders that can't be read.
            return None
