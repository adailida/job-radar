"""The one place that writes to the terminal, so a live line and messages never collide."""

import shutil
import sys
from collections.abc import Callable
from typing import TextIO


class Terminal:
    """Writes lines to the terminal, and can keep one live line at the bottom, redrawn in place.

    Everything that talks to the user (messages, questions, progress) goes
    through it. Before any line is written or a question asked, the live line
    is cleared, and it is drawn again after, so the two never run into each
    other. Without a live line it prints and reads exactly as `print` and
    `input` do. Stateful: holds the text of the live line.
    """

    CLEAR = "\r\x1b[K"  # back to the start of the line, then erase it

    def __init__(
        self,
        out: TextIO | None = None,
        tty: bool | None = None,
        read: Callable[[str], str] = input,
        width: Callable[[], int] = lambda: shutil.get_terminal_size().columns,
    ) -> None:
        """Keep where to write (stdout when None), whether it is a terminal, how to read, the width.

        `tty` is detected from the output when None; tests set it.
        """
        self._out = out
        self._tty = tty
        self._read = read
        self._width = width
        self._live: str | None = None

    @property
    def tty(self) -> bool:
        """Whether the output is a terminal that can redraw a line in place."""
        if self._tty is not None:
            return self._tty
        return bool(getattr(self._stream(), "isatty", lambda: False)())

    def write(self, text: str) -> None:
        """Print a line, clearing the live line first and drawing it again after."""
        self._hide()
        print(text, file=self._stream(), flush=True)
        self._draw()

    def read(self, prompt: str) -> str:
        """Ask a question and return the answer, with the live line cleared while it waits."""
        self._hide()
        try:
            return self._read(prompt)
        finally:
            self._draw()

    def live(self, text: str) -> None:
        """Show the live line, replacing the one before it, without ending the line."""
        self._hide()
        self._live = text
        self._draw()

    def settle(self, text: str) -> None:
        """Drop the live line and print this line in its place, for good."""
        self._hide()
        self._live = None
        print(text, file=self._stream(), flush=True)

    def _stream(self) -> TextIO:
        """Where to write: the stream it was given, or stdout as it is now."""
        return self._out if self._out is not None else sys.stdout

    def _hide(self) -> None:
        """Erase the live line from the screen, if there is one."""
        if self._live is not None:
            self._stream().write(self.CLEAR)

    def _draw(self) -> None:
        """Draw the live line, cut to fit the width so it can't wrap, if there is one."""
        if self._live is not None:
            stream = self._stream()
            stream.write(self.CLEAR + self._live[: max(self._width() - 1, 1)])
            stream.flush()
