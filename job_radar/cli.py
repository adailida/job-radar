"""The `job-radar` command."""

import argparse
import sys

from job_radar import __version__
from job_radar.clock import Clock
from job_radar.factory import AppFactory, Settings


class Cli:
    """Turns the command line into a call to the app and shows how it ended.

    Stateless: holds only the factory that builds the app.
    """

    @staticmethod
    def start() -> int:
        """Entry point of the `job-radar` command. Returns the exit code."""
        return Cli(AppFactory(Settings(), Clock())).main(sys.argv[1:])

    def __init__(self, factory: AppFactory) -> None:
        """Keep the factory that builds the app for each command."""
        self._factory = factory

    def main(self, argv: list[str]) -> int:
        """Parse the command line, run the chosen command, and return the exit code."""
        # TODO(task 4): add the run command.
        # TODO(task 13): add the runs and delete commands.
        parser = argparse.ArgumentParser(
            prog="job-radar", description="Job search and job-market trends."
        )
        parser.add_argument("--version", action="version", version=f"job-radar {__version__}")
        parser.parse_args(argv)
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(Cli.start())
