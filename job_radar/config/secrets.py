"""Reading secrets such as API keys, which are never committed."""

import os
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Secrets(Protocol):
    """Where API keys are read from. Stateless."""

    def get(self, name: str) -> str | None:
        """The secret's value, or None when it isn't set."""
        ...


class EnvSecrets:
    """Reads secrets from the environment, then from a `.env` file of NAME=value lines.

    The environment wins, so a key can be set for one command without editing
    the file. Stateless: holds only the file's path.
    """

    def __init__(self, path: Path) -> None:
        """Keep the path of the `.env` file."""
        self._path = path

    def get(self, name: str) -> str | None:
        """The value from the environment, else from the file; None when empty or missing."""
        if os.environ.get(name):
            return os.environ[name]
        if not self._path.is_file():
            return None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("\"'") or None
        return None
