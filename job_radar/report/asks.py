"""What employers in the user's searches ask for: requirements counted across matched jobs."""

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol, runtime_checkable

from job_radar.models import AskRow, Asks, Job, RequirementType, Window
from job_radar.report.trends import RunsSource, TrendBuilder


class RequirementNames:
    """Puts requirement names in one form, so spellings of the same thing count as one.

    Lowercase, hyphens and spacing tidied, outer brackets, quotes and trailing
    punctuation dropped, a trailing version number dropped ("Python 3",
    "Java 17", but not "ISO 27001"), a trailing "programming" or "language"
    dropped, and a few common aliases mapped ("Postgres" is "PostgreSQL").
    Stateless.
    """

    VERSION = re.compile(r"\s+v?\d{1,2}(\.\d+)*(\.x)?\+?$")
    FILLER = ("programming language", "programming", "language")
    ALIASES = {
        "postgres": "postgresql",
        "js": "javascript",
        "ts": "typescript",
        "k8s": "kubernetes",
        "gcp": "google cloud",
        "google cloud platform": "google cloud",
        "amazon web services": "aws",
        "golang": "go",
        "node": "node.js",
        "nodejs": "node.js",
        "react.js": "react",
        "reactjs": "react",
    }

    def key(self, name: str) -> str:
        """The canonical form of a requirement's name, for counting."""
        text = name.lower().replace("_", " ").replace("-", " ")
        text = " ".join(text.split()).strip("()[]\"' ").rstrip(".,;: ")
        text = self.VERSION.sub("", text)
        for filler in self.FILLER:
            if text.endswith(" " + filler):
                text = text[: -len(filler) - 1]
                break
        return self.ALIASES.get(text, text)


@dataclass
class _Tally:
    """Counts for one requirement while a window is counted: a short-lived holder, never shared.

    Stateful: holds the jobs asking for it, how postings spell it, and the
    years each job asks.
    """

    job_ids: set[str] = field(default_factory=set)
    spellings: Counter = field(default_factory=Counter)
    years: dict[str, int] = field(default_factory=dict)

    def name(self) -> str:
        """The most common spelling; on a tie, the first in alphabetical order."""
        return min(self.spellings.items(), key=lambda item: (-item[1], item[0]))[0]


class AskBuilder:
    """Counts what matched jobs ask for, in a rolling window, against the window before.

    The window is one trend period long (7, 30 or 91 days) and ends on the
    run's last day. A job counts on its trend date, as in the market trends.
    A share is the jobs asking for a requirement over the jobs with
    requirements in the window; jobs whose extraction failed are left out of
    both. Each type keeps its top N. Stateless: holds only the window length,
    how many rows a type gets, and how names are put in one form.
    """

    LENGTHS = {"week": 7, "month": 30, "quarter": 91}
    ORDER = (
        RequirementType.SKILL,
        RequirementType.TOOL,
        RequirementType.CERTIFICATION,
        RequirementType.YEARS,
    )
    LOW_SAMPLE = 20

    def __init__(self, period: str, per_type: int, names: RequirementNames) -> None:
        """Keep the window length for the period kind, the rows per type, and the names."""
        self._days = self.LENGTHS[period]
        self._per_type = per_type
        self._names = names

    def build(self, jobs: Iterable[Job], today: date) -> Asks:
        """The section for the window ending today; a job found in several runs counts once."""
        window = Window(start=today - timedelta(days=self._days - 1), end=today)
        previous = Window(
            start=window.start - timedelta(days=self._days), end=window.start - timedelta(days=1)
        )
        unique: dict[str, Job] = {}
        for job in jobs:
            if job.extraction is not None:
                unique.setdefault(job.id, job)
        now = self._inside(unique.values(), window)
        before = self._inside(unique.values(), previous)
        tallies = self._tallies(now)
        earlier = self._tallies(before)
        rows = []
        for kind in self.ORDER:
            ranked = sorted(
                ((key, tally) for key, tally in tallies.items() if key[0] is kind),
                key=lambda item: (-len(item[1].job_ids), item[1].name().lower()),
            )
            for key, tally in ranked[: self._per_type]:
                share = len(tally.job_ids) / len(now)
                change = None
                if before:
                    old = earlier.get(key)
                    change = (share - (len(old.job_ids) if old else 0) / len(before)) * 100
                years = list(tally.years.values())
                rows.append(
                    AskRow(
                        type=kind,
                        name=tally.name(),
                        jobs=len(tally.job_ids),
                        share=share,
                        change=change,
                        median_years=statistics.median(years) if years else None,
                        job_ids=tuple(sorted(tally.job_ids)),
                    )
                )
        return Asks(
            window=window,
            previous=previous,
            jobs=len(now),
            previous_jobs=len(before),
            rows=tuple(rows),
            low_sample=self.LOW_SAMPLE,
        )

    @staticmethod
    def _inside(jobs: Iterable[Job], window: Window) -> list[Job]:
        """The jobs whose trend date falls in the window."""
        return [job for job in jobs if window.start <= TrendBuilder.trend_date(job) <= window.end]

    def _tallies(self, jobs: list[Job]) -> dict[tuple[RequirementType, str], _Tally]:
        """Per requirement type and name: the jobs asking for it, its spellings, years asked."""
        tallies: defaultdict[tuple[RequirementType, str], _Tally] = defaultdict(_Tally)
        for job in jobs:
            for requirement in job.extraction.requirements:
                key = (requirement.type, self._names.key(requirement.name))
                if not key[1]:
                    continue
                tally = tallies[key]
                tally.job_ids.add(job.id)
                tally.spellings[" ".join(requirement.name.split())] += 1
                if requirement.years is not None:
                    tally.years[job.id] = max(requirement.years, tally.years.get(job.id, 0))
        return dict(tallies)


@runtime_checkable
class AskSource(Protocol):
    """Gives the report its what employers ask for section."""

    def asks(self) -> Asks:
        """The section, from earlier runs and this one."""
        ...


class MarketAsks:
    """Has the requirements counted over the runs the market sections look at.

    Free: it only counts what the extract step already found. Stateless: holds
    only where the runs come from, the builder, and the run's last day.
    """

    def __init__(self, runs: RunsSource, builder: AskBuilder, today: date) -> None:
        """Keep where the runs come from, the builder, and the day the window ends."""
        self._runs = runs
        self._builder = builder
        self._today = today

    def asks(self) -> Asks:
        """The section over every completed run's matched jobs, plus this run's."""
        jobs = [job for run in self._runs.runs() for job in run.jobs]
        return self._builder.build(jobs, self._today)
