"""Where the list of jobs the filter dropped goes."""

from collections import defaultdict
from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.models import DropList, DroppedJob
from job_radar.report.words import Words


@runtime_checkable
class DropLog(Protocol):
    """Keeps the list of jobs the filter dropped, so the user can look for misses."""

    def write(self, drops: DropList) -> None:
        """Store the run's dropped jobs."""
        ...


class FileDropLog:
    """Writes `dropped.md` in the run's folder: dropped jobs grouped by why, titles sorted.

    Groups go largest first; a group's heading names, for each search, the
    first criterion the job failed. Jobs posted before the window are only
    counted. Holds only its folder and how facts and dates are put into
    words; the file is the state.
    """

    NAME = "dropped.md"

    def __init__(self, folder: Path, words: Words) -> None:
        """Keep the run folder the list goes in, and how facts and dates are put into words."""
        self._folder = folder
        self._words = words

    def write(self, drops: DropList) -> None:
        """Write `dropped.md`, replacing any earlier one for this run."""
        (self._folder / self.NAME).write_text(self.render(drops), encoding="utf-8")

    def render(self, drops: DropList) -> str:
        """The list as Markdown."""
        window = drops.window
        summary = (
            f"Covers postings from {self._words.span(window.start, window.end)}. "
            f"{drops.checked} jobs checked, {drops.kept} kept, "
            f"{len(drops.dropped)} dropped by the searches."
        )
        if drops.before_window:
            summary += f" {drops.before_window} posted before the window aren't listed."
        lines = [f"# Dropped by the filter, {self._words.day(window.end, year=True)}", "", summary]
        groups: dict[tuple[str, ...], list[DroppedJob]] = defaultdict(list)
        for dropped in drops.dropped:
            groups[dropped.reasons].append(dropped)
        if not groups:
            lines.extend(["", "Nothing was dropped."])
        for reasons, jobs in sorted(groups.items(), key=lambda group: -len(group[1])):
            lines.extend(["", f"## {'; '.join(reasons)} ({len(jobs)})", ""])
            lines.extend(self._line(dropped) for dropped in sorted(jobs, key=self._title))
        return "\n".join(lines) + "\n"

    def _line(self, dropped: DroppedJob) -> str:
        """One dropped job: title, company, and what it says about where and how."""
        posting = dropped.job.postings[0]
        details = self._words.details(posting)
        return f"- {posting.title}, {posting.company}" + (f" ({details})" if details else "")

    @staticmethod
    def _title(dropped: DroppedJob) -> str:
        """The sort key: the title, any case."""
        return dropped.job.postings[0].title.casefold()
