"""The warnings of a run: problems that didn't stop it, collected in one place."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.model import Alert, AlertCode
from job_radar.prompter import Prompter


@runtime_checkable
class WarningLog(Protocol):
    """Collects a run's warnings, for the report's alerts and the end of the run (Repository)."""

    def warn(self, code: AlertCode, message: str) -> None:
        """Record one warning; the same warning twice is kept once."""
        ...

    def alerts(self) -> list[Alert]:
        """Every warning recorded, in the order recorded."""
        ...


class FileWarningLog:
    """Keeps a run's warnings in `warnings.jsonl` in its run folder, which stays after the run.

    A warning already there is not added again, so a resumed run that does a
    step over doesn't repeat it. Holds only its folder; the file is the state.
    """

    NAME = "warnings.jsonl"

    def __init__(self, folder: Path) -> None:
        """Keep the run folder the file goes in."""
        self._folder = folder

    def warn(self, code: AlertCode, message: str) -> None:
        """Add the warning after the ones already there, unless it is one of them."""
        alert = Alert(code=code, message=message)
        if alert in self.alerts():
            return
        with (self._folder / self.NAME).open("a", encoding="utf-8") as file:
            file.write(alert.model_dump_json() + "\n")

    def alerts(self) -> list[Alert]:
        """Every recorded warning; none when the run had none."""
        path = self._folder / self.NAME
        if not path.is_file():
            return []
        with path.open(encoding="utf-8") as lines:
            return [Alert.model_validate_json(line) for line in lines if line.strip()]


class TerminalWarnings:
    """Tells warnings in the terminal, for when no run is going on to record them in.

    Each warning is told once, however often it comes up. Stateful: remembers
    the warnings it has told, for as long as the command runs.
    """

    def __init__(self, prompter: Prompter) -> None:
        """Keep who to tell, and start with nothing told."""
        self._prompter = prompter
        self._told: list[Alert] = []

    def warn(self, code: AlertCode, message: str) -> None:
        """Tell the warning, unless it was told already."""
        alert = Alert(code=code, message=message)
        if alert not in self._told:
            self._told.append(alert)
            self._prompter.tell(f"Warning: {message}")

    def alerts(self) -> list[Alert]:
        """The warnings told so far."""
        return list(self._told)
