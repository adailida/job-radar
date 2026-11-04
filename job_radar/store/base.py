"""Run data interface (design section 5).

Only the methods the walking skeleton calls. History, caches, pending jobs, spend
and delete are added by the tasks that need them (10 to 19).
"""

from typing import Protocol

from job_radar.model import Classification, Extraction, Job, Match, Run
from job_radar.sources.base import RawSink


class RunStore(Protocol):
    def start(self, run: Run) -> None: ...

    def raw_sink(self, run_id: str, source: str) -> RawSink: ...

    def save_jobs(self, run_id: str, jobs: list[Job]) -> None: ...

    def save_classifications(self, run_id: str, items: list[Classification]) -> None: ...

    def save_matches(self, run_id: str, items: list[Match]) -> None: ...

    def save_extractions(self, run_id: str, items: list[Extraction]) -> None: ...

    def save_report(self, run_id: str, text: str) -> None: ...

    def finish(self, run: Run) -> None: ...

    def runs(self) -> list[Run]: ...
