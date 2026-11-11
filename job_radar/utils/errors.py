"""The errors a run expects: each says what's wrong and what to do about it."""


class JobRadarError(Exception):
    """An error the app expects and explains, so the user sees its message, not a traceback.

    Anything else that stops a run is unexpected: a bug, written in full to
    `error.log`.
    """

    @staticmethod
    def describe(error: BaseException) -> str:
        """Any error in one line: an expected error's message; anything else with its type."""
        said = " ".join(str(error).split())
        if isinstance(error, JobRadarError):
            return said or type(error).__name__
        return f"{type(error).__name__}: {said}" if said else type(error).__name__


class SetupError(JobRadarError):
    """A run can't start: a file, a setting, a key, a tool or another run is in the way.

    Its message names what's at fault and how to fix it.
    """
