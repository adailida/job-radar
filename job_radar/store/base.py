"""The interfaces for saving run data and reading it back."""

from datetime import datetime
from typing import Protocol

from job_radar.model import (
    Classification,
    Extraction,
    Job,
    Match,
    Run,
    RunStatus,
    SourceResult,
)
from job_radar.sources.base import RawPage


class RunWriter(Protocol):
    """Saves what one run produces, from its start to its finish.

    Stateful: owns the record of one run, got from `RunStore.start` and dropped
    when the run finishes. It is the only thing that changes that record; others
    read it through `run`. Nothing it saves can end up in another run.
    """

    @property
    def run(self) -> Run:
        """The run as last saved."""
        ...

    def save_raw_page(self, page: RawPage) -> None:
        """Keep one raw response page as received from a source."""
        ...

    def save_source_results(self, results: list[SourceResult]) -> None:
        """Record what each source did: queries, postings fetched, credits.

        Saved as soon as fetching ends, so a run that fails later still shows
        what it spent.
        """
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

    def finish(self, status: RunStatus, finished_at: datetime) -> None:
        """Close the run as completed or failed. Nothing can be saved after this."""
        ...


class RunStore(Protocol):
    """Where all runs are kept: starts new ones and reads earlier ones back.

    Keeps no state in memory: what it has saved is the state. One store serves
    every run, so it holds no current run; `start` hands out a writer for that.
    """

    # TODO(task 10): add history, cached LLM results, pending jobs and delete.
    # TODO(task 19): add the spend ledger.

    def start(self, run: Run) -> RunWriter:
        """Record a new run as running and return the writer for its data."""
        ...

    def runs(self) -> list[Run]:
        """Every kept run, whatever its status."""
        ...
