"""Test doubles shared by several test files."""

from datetime import date, datetime, timedelta, timezone

from job_radar.clock import Clock
from job_radar.model import Job, Location, Posting, Report, StepCount, Window, WorkMode


class FixedClock(Clock):
    """A clock stopped at one moment, so run folders and dates are predictable."""

    def __init__(self, hour: int = 10, day: int = 5):
        """Stop the clock at that hour of that day in November 2026."""
        self._now = datetime(2026, 11, day, hour, 0, 0, tzinfo=timezone(timedelta(hours=-5)))

    def now(self) -> datetime:
        """Always the same moment."""
        return self._now


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
WINDOW = Window(start=date(2026, 10, 22), end=date(2026, 11, 5))


class FakePrompter:
    """A user who gives set answers, and a record of everything said to them."""

    def __init__(self, *answers: bool):
        """Keep the answers to give, in order."""
        self._answers = list(answers)
        self.told: list[str] = []
        self.asked: list[str] = []

    def tell(self, message: str) -> None:
        """Remember the message."""
        self.told.append(message)

    def confirm(self, question: str, default: bool = True) -> bool:
        """Remember the question and give the next answer."""
        self.asked.append(question)
        return self._answers.pop(0)

    def choose(self, question, choices, default: str) -> str:
        """Remember the question and give the next answer."""
        self.asked.append(question)
        return self._answers.pop(0)


class FakeHistory:
    """Run history with a set last window."""

    def __init__(self, last: Window | None):
        """Keep the last completed run's window."""
        self._last = last

    def last_window(self) -> Window | None:
        """The set window."""
        return self._last


class MemoryDropLog:
    """A drop log that keeps the list instead of writing a file."""

    def __init__(self):
        """Start with nothing written."""
        self.drops = None

    def write(self, drops) -> None:
        """Keep the list."""
        self.drops = drops


class MemorySpendLog:
    """A spend log that keeps records in memory."""

    def __init__(self, *spends):
        """Start with these records."""
        self.written = list(spends)

    def write(self, spend) -> None:
        """Keep the record."""
        self.written.append(spend)

    def spends(self):
        """The records kept."""
        return list(self.written)


class NoCost:
    """A cost check with no paid sources: approves nothing, asks nothing."""

    def check(self, window):
        """No approvals."""
        return []


class MemoryPendingLog:
    """A pending log that keeps carried-over jobs in memory."""

    def __init__(self, *jobs):
        """Start with these jobs."""
        self.kept = list(jobs)

    def add(self, jobs) -> None:
        """Keep the jobs, each once by id."""
        known = {job.id for job in self.kept}
        self.kept += [job for job in jobs if job.id not in known]

    def jobs(self):
        """The jobs kept."""
        return list(self.kept)


def guard(*answers: str):
    """A usage-limit guard with a user giving these answers and an in-memory pending log."""
    from job_radar.usage import UsageLimitGuard

    return UsageLimitGuard(FakePrompter(*answers), MemoryPendingLog())


class NoTrends:
    """A trends source with nothing to show."""

    def trends(self):
        """No trends section."""
        return None


class NoAsks:
    """A what employers ask for source with nothing to show."""

    def asks(self):
        """No what employers ask for section."""
        return None


class NoGaps:
    """An experience to gain source with nothing to show."""

    def gaps(self, asks):
        """An empty section."""
        from job_radar.model import Gaps

        return Gaps(rows=())
