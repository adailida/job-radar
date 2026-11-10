"""Where an unexpected error's full details go, so the terminal shows one line."""

import traceback
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ErrorLog(Protocol):
    """Keeps the full details of an unexpected error (Repository)."""

    def write(self, error: BaseException) -> str:
        """Record the error with its traceback, and say where it is."""
        ...


class FileErrorLog:
    """Writes an unexpected error's traceback to `error.log` in one folder, replacing any before.

    The folder is the run's, or the output folder when no run folder exists
    yet. Holds only its folder; the file is the state.
    """

    NAME = "error.log"

    def __init__(self, folder: Path) -> None:
        """Keep the folder the file goes in."""
        self._folder = folder

    def write(self, error: BaseException) -> str:
        """Write the error's type, message and traceback; the file's path."""
        path = self._folder / self.NAME
        self._folder.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(traceback.format_exception(error)), encoding="utf-8")
        return str(path)
