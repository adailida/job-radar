"""Prompter interface (design section 7): runs are interactive, tests cannot type."""

from collections.abc import Sequence
from typing import Protocol


class Prompter(Protocol):
    def ask(self, question: str) -> str:
        """Free text answer; empty string when the user gives none."""
        ...

    def choose(self, question: str, options: Sequence[str], default: str | None = None) -> str:
        """One of `options`; `default` when the user just presses Enter."""
        ...
