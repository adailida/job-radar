"""How many postings each source gave in a run, for the report's header."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.models import SourceCount


@runtime_checkable
class SourceCountLog(Protocol):
    """Keeps how many postings each source gave in a run (Repository)."""

    def write(self, counts: Sequence[SourceCount]) -> None:
        """Record every source's count, replacing any earlier record."""
        ...

    def counts(self) -> list[SourceCount]:
        """Every source's count, in the order recorded."""
        ...


class FileSourceCountLog:
    """Keeps a run's posting counts in `source_counts.jsonl` in its run folder, which stays.

    Holds only its folder; the file is the state.
    """

    NAME = "source_counts.jsonl"

    def __init__(self, folder: Path) -> None:
        """Keep the run folder the file goes in."""
        self._folder = folder

    def write(self, counts: Sequence[SourceCount]) -> None:
        """Write every source's count, replacing the file."""
        lines = "".join(count.model_dump_json() + "\n" for count in counts)
        (self._folder / self.NAME).write_text(lines, encoding="utf-8")

    def counts(self) -> list[SourceCount]:
        """Every recorded count; none when nothing was recorded."""
        path = self._folder / self.NAME
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [SourceCount.model_validate(json.loads(line)) for line in lines if line.strip()]
