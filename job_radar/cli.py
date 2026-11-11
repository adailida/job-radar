"""The `job-radar` command."""

import argparse
import sys
from pathlib import Path

from job_radar import __version__
from job_radar.app.app_factory import AppFactory
from job_radar.config.secrets import EnvSecrets
from job_radar.config.settings import SettingsFile
from job_radar.utils.clock import Clock
from job_radar.utils.errors import JobRadarError, SetupError
from job_radar.utils.prompter import TerminalPrompter


class Cli:
    """Turns the command line into a call to the app and shows how it ended.

    Every way a run can end comes out as a short message and an exit code,
    never a traceback: a setup error names what's at fault and how to fix it;
    an unexpected error says where its details were written. Stateless: holds
    only the factory that builds the app.
    """

    LOCAL = Path("config_local")  # the user's folder: CV, preferences, profile, settings, keys

    @staticmethod
    def start() -> int:
        """Entry point of the `job-radar` command: reads the settings, then runs. The exit code."""
        try:
            settings = SettingsFile(Cli.LOCAL / "settings.yaml").load()
        except SetupError as error:
            print(f"Could not set up the run: {error}")
            return 2
        secrets = EnvSecrets(Cli.LOCAL / ".env")
        factory = AppFactory(settings, Cli.LOCAL, Clock(), TerminalPrompter(), secrets)
        return Cli(factory).main(sys.argv[1:])

    def __init__(self, factory: AppFactory) -> None:
        """Keep the factory that builds the app for each command."""
        self._factory = factory

    def main(self, argv: list[str]) -> int:
        """Parse the command line, run the chosen command, and return the exit code.

        Exit codes: 0 when the command succeeded or the user called it off, 1
        when a run failed or stopped, or a run to delete doesn't exist, 2 when
        the run could not be set up or another run is in progress.
        """
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
        runs = commands.add_parser("runs", help="list earlier runs, newest first")
        runs.add_argument("--demo", action="store_true", help="list demo runs instead")
        delete = commands.add_parser("delete", help="delete earlier runs, after asking")
        delete.add_argument("run_ids", nargs="*", metavar="run-id", help="as `runs` lists it")
        delete.add_argument("--all", action="store_true", help="delete every run")
        delete.add_argument("--demo", action="store_true", help="delete demo runs instead")
        args = parser.parse_args(argv)
        if args.command == "runs":
            return self._factory.runs_command(demo=args.demo).show()
        if args.command == "delete":
            return self._factory.runs_command(demo=args.demo).delete(args.run_ids, every=args.all)
        if args.command != "run":
            parser.print_help()
            return 0
        try:
            app = self._factory.create(demo=args.demo)
        except SetupError as error:
            print(f"Could not set up the run: {error}")
            return 2
        except Exception as error:
            return self._unexpected("Could not set up the run", error, 2)
        try:
            result = app.run()
        except SetupError as error:
            print(f"Could not start the run: {error}")
            return 2
        except JobRadarError as error:
            print(f"Run stopped: {error}")
            return 1
        except Exception as error:
            return self._unexpected("Run stopped", error, 1)
        except KeyboardInterrupt:
            print(
                "\nStopped by you. A run that had started is kept: "
                "run the same command to resume it."
            )
            return 1
        print(result.message())
        return result.exit_code()

    def _unexpected(self, what: str, error: Exception, code: int) -> int:
        """Say in one line that an unexpected error stopped things, and where its details are."""
        said = JobRadarError.describe(error)
        try:
            where = f" Details in {self._factory.error_log().write(error)}"
        except OSError:
            where = ""
        print(f"{what}: unexpected error ({said}).{where}")
        return code


if __name__ == "__main__":
    raise SystemExit(Cli.start())
