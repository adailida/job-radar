"""Where finished reports go."""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ReportWriter(Protocol):
    """Stores a finished report and says where it is. Stateless."""

    def write(self, text: str) -> str:
        """Store the report and return its location."""
        ...


class FileReportWriter:
    """Writes the report as `report.md` in the run's folder.

    Holds only its folder; the file is the state.
    """

    def __init__(self, folder: Path) -> None:
        """Keep the run folder the report goes in."""
        self._folder = folder

    def write(self, text: str) -> str:
        """Write `report.md` and return its path."""
        # TODO(task 8): write the file.
        raise NotImplementedError
