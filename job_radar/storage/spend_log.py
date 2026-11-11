"""What paid sources spent in a run, kept in its run folder."""

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.models import Spend


@runtime_checkable
class SpendLog(Protocol):
    """Keeps what each paid source spent in a run (Repository)."""

    def write(self, spend: Spend) -> None:
        """Record one source's spend."""
        ...

    def spends(self) -> list[Spend]:
        """Every source's spend in this run, in the order recorded."""
        ...


class FileSpendLog:
    """Keeps a run's spend in `spend.jsonl` in its run folder, which stays after the run.

    Holds only its folder; the file is the state.
    """

    NAME = "spend.jsonl"

    def __init__(self, folder: Path) -> None:
        """Keep the run folder the file goes in."""
        self._folder = folder

    def write(self, spend: Spend) -> None:
        """Add one source's spend, replacing an earlier record for the same source."""
        kept = [s for s in self.spends() if s.approval.source != spend.approval.source]
        lines = "".join(s.model_dump_json() + "\n" for s in (*kept, spend))
        (self._folder / self.NAME).write_text(lines, encoding="utf-8")

    def spends(self) -> list[Spend]:
        """Every recorded spend; none when nothing paid ran."""
        path = self._folder / self.NAME
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [Spend.model_validate(json.loads(line)) for line in lines if line.strip()]
