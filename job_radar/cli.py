"""Command line entry point: `job-radar`."""

import argparse

from job_radar import __version__


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and run the chosen command. Returns the exit code."""
    # TODO(task 5): add the run command.
    # TODO(task 10): add the runs and delete commands.
    parser = argparse.ArgumentParser(
        prog="job-radar", description="Job search and job-market trends."
    )
    parser.add_argument("--version", action="version", version=f"job-radar {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
