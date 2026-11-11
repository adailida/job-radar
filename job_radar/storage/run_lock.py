"""One run at a time: a lock file holding the running process's id."""

import os
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from job_radar.utils.errors import SetupError


class RunInProgress(SetupError):
    """Another run holds the lock, and its process is still going."""


@runtime_checkable
class RunLock(Protocol):
    """Lets one run go at a time: taken when a run starts, released when it ends, however."""

    def __enter__(self) -> Self:
        """Take the lock, or raise `RunInProgress` when another run holds it."""
        ...

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """Release the lock."""
        ...


class FileRunLock:
    """A lock file in the output folder that holds the id of the process running.

    A lock whose process no longer exists, left by a run that was killed, is
    removed and taken. Holds only the file's path, this process's id and how
    to tell whether a process is alive; the file is the state.
    """

    NAME = "run.lock"

    def __init__(
        self,
        folder: Path,
        pid: int | None = None,
        alive: Callable[[int], bool] | None = None,
    ) -> None:
        """Keep the folder the lock goes in, this process's id, and how to check a process."""
        self._path = folder / self.NAME
        self._pid = os.getpid() if pid is None else pid
        self._alive = alive or self.process_exists

    def __enter__(self) -> Self:
        """Create the lock file with this process's id, removing a stale one first."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                with self._path.open("x", encoding="utf-8") as file:
                    file.write(f"{self._pid}\n")
                return self
            except FileExistsError:
                holder = self._holder()
                if holder is not None and self._alive(holder):
                    raise RunInProgress(
                        f"Another run is in progress (pid {holder}). Wait for it to finish; "
                        f"if no run is going, delete {self._path}"
                    ) from None
                self._path.unlink(missing_ok=True)
        raise RunInProgress(f"Another run took the lock at {self._path} just now")

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """Remove the lock file, if it is still this process's."""
        if self._holder() == self._pid:
            self._path.unlink(missing_ok=True)

    def _holder(self) -> int | None:
        """The process id in the lock file; None when there is no file or it can't be read."""
        try:
            pid = int(self._path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 0 else None

    @staticmethod
    def process_exists(pid: int) -> bool:
        """Whether a process with this id is running."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # it exists, under another user
        return True
