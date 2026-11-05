"""Talking to the user in the terminal while a run is set up."""

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class Prompter(Protocol):
    """Tells the user things and asks them questions. Stateless."""

    def tell(self, message: str) -> None:
        """Show a message."""
        ...

    def confirm(self, question: str) -> bool:
        """Ask a yes or no question; yes is the default."""
        ...


class TerminalPrompter:
    """Asks in the terminal. With no input to read, as in a script, takes the default.

    Stateless: holds only how it reads and writes lines.
    """

    YES = ("y", "yes", "")
    NO = ("n", "no")

    def __init__(
        self, read: Callable[[str], str] = input, write: Callable[[str], None] = print
    ) -> None:
        """Keep how to read an answer and how to write a line, so tests can replace them."""
        self._read = read
        self._write = write

    def tell(self, message: str) -> None:
        """Print the message."""
        self._write(message)

    def confirm(self, question: str) -> bool:
        """Ask until the answer is y or n; Enter means y."""
        while True:
            try:
                answer = self._read(f"{question} (y/n, Enter for y) ").strip().lower()
            except EOFError:
                return True
            if answer in self.YES:
                return True
            if answer in self.NO:
                return False
            self._write("Please answer y or n.")
