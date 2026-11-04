"""Command line entry point. Subcommands arrive with the tasks that implement them."""

import argparse

from job_radar import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="job-radar", description="Job search and job-market trends."
    )
    parser.add_argument("--version", action="version", version=f"job-radar {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
