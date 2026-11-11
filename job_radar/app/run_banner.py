"""The start banner: what a run is about to do, shown before its first step."""

from collections.abc import Mapping, Sequence

from job_radar.models import RunWindows, Window, WindowReason
from job_radar.utils.clock import Clock
from job_radar.utils.progress import Progress


class RunBanner:
    """Tells the user what the run will do: config, searches, sources and dates, limits, steps.

    Shown through the progress reporter once the dates and the spend are
    agreed, just before the pipeline starts. Stateless: holds only what the
    run is set up with, the clock and who it shows the lines to.
    """

    def __init__(
        self,
        config: str,
        searches: Sequence[str],
        sources: Mapping[str, str],
        progress: Progress,
        clock: Clock,
        model: str | None = None,
        ask_above_credits: int | None = None,
        ask_above_jobs: int | None = None,
        demo: bool = False,
    ) -> None:
        """Keep the config folder, the searches' names, the sources' labels by name, and the limits.

        `model` and the limits are None for a run that has no LLM or no paid
        source, and their parts are left out.
        """
        self._config = config
        self._searches = list(searches)
        self._sources = sources
        self._progress = progress
        self._clock = clock
        self._model = model
        self._credits = ask_above_credits
        self._jobs = ask_above_jobs
        self._demo = demo

    def show(self, windows: RunWindows, steps: Sequence[str], resuming: bool = False) -> None:
        """Show the banner for a run with these windows and steps."""
        for line in self.lines(windows, steps, resuming):
            self._progress.note(line)

    def lines(self, windows: RunWindows, steps: Sequence[str], resuming: bool = False) -> list[str]:
        """The banner's lines: heading, config, limits (if any), sources and the steps."""
        now = self._clock.now()
        flags = (" (demo)" if self._demo else "") + (" (resuming)" if resuming else "")
        count = len(self._searches)
        searches = f"{count} search{'' if count == 1 else 'es'} ({', '.join(self._searches)})"
        config = f"Config: {self._config} · {searches}"
        config += f" · model {self._model}" if self._model else " · no LLM, keyword scoring"
        lines = [f"job-radar run{flags}, {now:%b} {now.day} {now:%H:%M}", config]
        limits = self._limits()
        if limits:
            lines.append(f"Limits: ask above {limits}")
        lines.append(
            "Sources: " + " · ".join(self._source(windows, name) for name in self._names(windows))
        )
        names = [step.replace("_", " ") for step in steps]
        lines.append(f"{len(names)} steps: {', '.join(names)}")
        return lines

    def _limits(self) -> str:
        """The limits a run asks above: credits for a paid source, jobs for Claude."""
        parts = []
        if self._credits is not None:
            parts.append(f"{self._credits:,} credits")
        if self._jobs is not None:
            parts.append(f"{self._jobs:,} jobs for Claude")
        return ", ".join(parts)

    def _names(self, windows: RunWindows) -> list[str]:
        """The sources in the order the run lists them."""
        listed = [source.source for source in windows.sources]
        return listed or list(self._sources)

    def _source(self, windows: RunWindows, name: str) -> str:
        """One source: its name, its own dates, and why they are not the usual ones."""
        label = self._sources.get(name, name)
        text = f"{label} {self._dates(windows.of(name))}"
        found = next((s for s in windows.sources if s.source == name), None)
        if found is not None and found.reason is WindowReason.CATCHING_UP:
            text += " (catching up)"
        return text

    @staticmethod
    def _dates(window: Window) -> str:
        """A window as "Nov 10 to 12", "Oct 29 to Nov 12", or "Nov 12" for one day."""
        start, end = window.start, window.end
        if start == end:
            return f"{start:%b} {start.day}"
        same_month = (start.year, start.month) == (end.year, end.month)
        return f"{start:%b} {start.day} to " + (
            f"{end.day}" if same_month else f"{end:%b} {end.day}"
        )
