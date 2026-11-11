"""The current time, kept in one place."""

from datetime import datetime


class Clock:
    """Tells the current time, so tests can replace it with a fixed one. Stateless."""

    def now(self) -> datetime:
        """The current local time, with its timezone."""
        return datetime.now().astimezone()

    def stamp(self) -> str:
        """The current time as a folder name, to the second, e.g. "2026-11-05T10-00-00"."""
        return self.now().strftime("%Y-%m-%dT%H-%M-%S")
