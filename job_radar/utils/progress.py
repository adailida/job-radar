"""Showing what a run is doing: which step is running, and how far along it is."""

from typing import Protocol, runtime_checkable

from job_radar.utils.clock import Clock
from job_radar.utils.terminal import Terminal


@runtime_checkable
class Progress(Protocol):
    """Reports a run's progress to the user: a line per step, and live counts inside slow ones.

    The pipeline reports each step's start and end; the steps and sources that
    take long report what they are up to with `detail`.
    """

    def note(self, text: str) -> None:
        """Show a line that stays, such as the start banner."""
        ...

    def begin(self, number: int, total: int, name: str) -> None:
        """A step starts: it is number `number` of `total`."""
        ...

    def detail(self, text: str) -> None:
        """What the current step is doing now, such as "5 of 11"."""
        ...

    def done(self, summary: str) -> None:
        """The current step finished, with what it gave, such as "470 jobs"."""
        ...

    def skipped(self, number: int, total: int, name: str) -> None:
        """A step an earlier attempt already saved, left out of a resumed run."""
        ...

    def failed(self) -> None:
        """The current step failed."""
        ...


class NoProgress:
    """Shows nothing: for `--quiet`, and where progress doesn't matter. Stateless."""

    def note(self, text: str) -> None:
        """Show nothing."""

    def begin(self, number: int, total: int, name: str) -> None:
        """Show nothing."""

    def detail(self, text: str) -> None:
        """Show nothing."""

    def done(self, summary: str) -> None:
        """Show nothing."""

    def skipped(self, number: int, total: int, name: str) -> None:
        """Show nothing."""

    def failed(self) -> None:
        """Show nothing."""


class _StepLines:
    """What the terminal and line progress share: a numbered line per step, timed.

    Stateful: holds the current step's label and when it started.
    """

    NAME_WIDTH = 15  # the longest step name, so the lines line up

    def __init__(self, terminal: Terminal, clock: Clock) -> None:
        """Keep where to write and the clock that times the steps."""
        self._terminal = terminal
        self._clock = clock
        self._label = ""
        self._started = clock.now()

    def note(self, text: str) -> None:
        """Print a line that stays."""
        self._terminal.write(text)

    def begin(self, number: int, total: int, name: str) -> None:
        """Start timing a step."""
        self._label = self._format(number, total, name)
        self._started = self._clock.now()

    def done(self, summary: str) -> None:
        """Settle the step's line as done, with what it gave and how long it took."""
        self._terminal.settle(f"{self._label}done: {summary} ({self._took()})")

    def skipped(self, number: int, total: int, name: str) -> None:
        """Print that the step was saved by an earlier attempt."""
        self._terminal.settle(f"{self._format(number, total, name)}saved earlier")

    def failed(self) -> None:
        """Settle the step's line as failed, with how long it ran."""
        self._terminal.settle(f"{self._label}failed ({self._took()})")

    def _format(self, number: int, total: int, name: str) -> str:
        """The start of a step's line: "[2/13] convert", padded."""
        position = f"[{number:>{len(str(total))}}/{total}]"
        return f"{position} {name.replace('_', ' '):<{self.NAME_WIDTH}} "

    def _took(self) -> str:
        """How long the current step has run, e.g. "0.1s" or "1m 05s"."""
        seconds = (self._clock.now() - self._started).total_seconds()
        if seconds < 60:
            return f"{seconds:.1f}s"
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"


class TerminalProgress(_StepLines):
    """Shows the current step on one line that updates in place, then settles to its done line.

    For a terminal. Stateful: holds the current step's label and start time
    (the live line itself is held by the terminal).
    """

    def begin(self, number: int, total: int, name: str) -> None:
        """Start the step's live line."""
        super().begin(number, total, name)
        self._terminal.live(f"{self._label}running")

    def detail(self, text: str) -> None:
        """Update the live line."""
        self._terminal.live(f"{self._label}{text}")


class LineProgress(_StepLines):
    """Prints one line per update, at most one every few seconds, then the step's done line.

    For output that isn't a terminal, such as a pipe or a file, where lines
    can't be redrawn. The first update of a step is always shown. Stateful:
    holds the current step's label and start time, and when it last printed.
    """

    def __init__(self, terminal: Terminal, clock: Clock, interval: float = 5.0) -> None:
        """Keep where to write, the clock, and the fewest seconds between two updates."""
        super().__init__(terminal, clock)
        self._interval = interval
        self._printed = None

    def begin(self, number: int, total: int, name: str) -> None:
        """Start the step; its first update will be shown."""
        super().begin(number, total, name)
        self._printed = None

    def detail(self, text: str) -> None:
        """Print the update unless one was printed less than the interval ago."""
        now = self._clock.now()
        if self._printed is None or (now - self._printed).total_seconds() >= self._interval:
            self._printed = now
            self._terminal.write(f"{self._label}{text}")
