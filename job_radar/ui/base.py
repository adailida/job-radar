"""The interface for asking the user questions during a run."""

from collections.abc import Sequence
from typing import Protocol


class Prompter(Protocol):
    """Asks the user for input during a run, such as a missing profile field or a go-ahead.

    Swappable, so tests can supply scripted answers instead of typing.

    Stateless: returns each answer to its caller and remembers none.
    """

    def ask(self, question: str) -> str:
        """Ask for free text. Returns an empty string when the user gives none."""
        ...

    def choose(self, question: str, options: Sequence[str], default: str | None = None) -> str:
        """Ask the user to pick one of `options`. Returns `default` when they just press Enter."""
        ...
