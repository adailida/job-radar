"""The current time, kept in one place."""

from datetime import datetime


class Clock:
    """Tells the current time, so tests can replace it with a fixed one. Stateless."""

    def now(self) -> datetime:
        """The current local time, with its timezone."""
        return datetime.now().astimezone()

    def stamp(self) -> str:
        """The current time as a folder name, e.g. "2026-11-05T10-00"."""
        # TODO(task 4): format now() for folder names.
        raise NotImplementedError
