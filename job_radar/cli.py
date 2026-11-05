"""The `job-radar` command."""

import argparse
import sys

from job_radar import __version__
from job_radar.clock import Clock
from job_radar.factory import AppFactory, Settings
from job_radar.prompter import TerminalPrompter


class Cli:
    """Turns the command line into a call to the app and shows how it ended.

    Stateless: holds only the factory that builds the app.
    """

    @staticmethod
    def start() -> int:
        """Entry point of the `job-radar` command. Returns the exit code."""
        return Cli(AppFactory(Settings(), Clock(), TerminalPrompter())).main(sys.argv[1:])

    def __init__(self, factory: AppFactory) -> None:
        """Keep the factory that builds the app for each command."""
        self._factory = factory

    def main(self, argv: list[str]) -> int:
        """Parse the command line, run the chosen command, and return the exit code.

        Exit codes: 0 when the run succeeded or the user called it off, 1 when
        a step failed, 2 when the run could not be set up.
        """
        # TODO(task 13): add the runs and delete commands.
        parser = argparse.ArgumentParser(
            prog="job-radar", description="Job search and job-market trends."
        )
        parser.add_argument("--version", action="version", version=f"job-radar {__version__}")
        commands = parser.add_subparsers(dest="command", title="commands")
        run = commands.add_parser("run", help="fetch jobs, recommend the best, write a report")
        run.add_argument(
            "--demo",
            action="store_true",
            help="use made-up postings and a made-up profile: no network, no LLM",
        )
        args = parser.parse_args(argv)
        if args.command != "run":
            parser.print_help()
            return 0
        try:
            app = self._factory.create(demo=args.demo)
        except Exception as error:
            # TODO(task 24): name the setting or file at fault, with how to fix it.
            print(f"Could not set up the run: {str(error) or type(error).__name__}")
            return 2
        result = app.run()
        print(result.message())
        return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(Cli.start())
