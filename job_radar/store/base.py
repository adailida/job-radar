"""The interfaces for saving run data and reading it back."""

from typing import Protocol

from job_radar.model import Classification, Extraction, Job, Match, Run
from job_radar.sources.base import RawPage


class RunWriter(Protocol):
    """Saves what one run produces, from its start to its finish.

    Got from `RunStore.start`; it already knows its run, so nothing it saves
    can end up in another run.
    """

    def save_raw_page(self, page: RawPage) -> None:
        """Keep one raw response page as received from a source."""
        ...

    def save_jobs(self, jobs: list[Job]) -> None:
        """Keep the run's jobs after duplicates across sources are merged."""
        ...

    def save_classifications(self, items: list[Classification]) -> None:
        """Keep the labels given to the run's jobs."""
        ...

    def save_matches(self, items: list[Match]) -> None:
        """Keep which searches each matched job satisfies."""
        ...

    def save_extractions(self, items: list[Extraction]) -> None:
        """Keep the requirements found in the matched jobs."""
        ...

    def save_report(self, text: str) -> None:
        """Keep the run's rendered report."""
        ...

    def finish(self, run: Run) -> None:
        """Record the run's final state: status, finish time, how each source did.

        Takes the whole Run because runs are immutable; the final state is a new
        Run with the same id. Raises if the id is not this writer's run.
        """
        ...


class RunStore(Protocol):
    """Where all runs are kept: starts new ones and reads earlier ones back."""

    # TODO(task 10): add history, cached LLM results, pending jobs and delete.
    # TODO(task 19): add the spend ledger.

    def start(self, run: Run) -> RunWriter:
        """Record a new run as running and return the writer for its data."""
        ...

    def runs(self) -> list[Run]:
        """Every kept run, whatever its status."""
        ...
