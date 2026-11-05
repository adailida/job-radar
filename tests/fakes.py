"""Test doubles shared by several test files."""

from datetime import date, datetime, timedelta, timezone

from job_radar.clock import Clock
from job_radar.model import Job, Location, Posting, Report, StepCount, WorkMode


class FixedClock(Clock):
    """A clock stopped at one moment, so run folders and dates are predictable."""

    NOW = datetime(2026, 11, 5, 10, 0, 0, tzinfo=timezone(timedelta(hours=-5)))

    def now(self) -> datetime:
        """Always the same moment."""
        return self.NOW


class FakeStep:
    """A step that gives fixed items, or raises, and remembers what it was given."""

    def __init__(self, name: str, gives: list | None = None, error: Exception | None = None):
        """Keep the step's name and either what it gives or the error it raises."""
        self.name = name
        self.output = type(gives[0]) if gives else StepCount
        self._gives = gives or []
        self._error = error
        self.received: list | None = None

    def run(self, data: list) -> list:
        """Remember the input, then raise or give the fixed items."""
        self.received = data
        if self._error:
            raise self._error
        return self._gives


class FakeStats:
    """Run stats with a fixed funnel."""

    def __init__(self, funnel: list[StepCount]):
        """Keep the funnel to report."""
        self._funnel = funnel

    def funnel(self) -> list[StepCount]:
        """The fixed funnel."""
        return self._funnel


class MemoryWriter:
    """A report writer that keeps the text instead of writing a file."""

    def __init__(self):
        """Start with no report written."""
        self.text: str | None = None

    def write(self, text: str) -> str:
        """Keep the text and give a made-up location."""
        self.text = text
        return "memory/report.md"


def posting(source_id: str, title: str = "Data Engineer", source: str = "demo") -> Posting:
    """A minimal posting with the given id and title."""
    return Posting(
        source=source,
        source_id=source_id,
        title=title,
        company="Example Org",
        locations=(Location(text="Remote"),),
        work_mode=WorkMode.REMOTE,
        url=f"https://example.org/jobs/{source_id}",
        description="",
    )


def job(source_id: str, title: str = "Data Engineer") -> Job:
    """A job made of one minimal posting."""
    p = posting(source_id, title)
    return Job(id=p.key, keys=(p.key,), postings=(p,), first_seen=date(2026, 11, 5))


REPORT = Report(location="out/report.md", summary="3 jobs recommended")
