"""Source interface (design section 4)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from job_radar.model import Posting, Search, Window


@dataclass(frozen=True)
class FetchPlan:
    """What one source will fetch: one query per search, over the window."""

    source: str
    window: Window
    queries: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RawPage:
    """One response page exactly as the source returned it."""

    source: str
    page: int
    body: bytes


# Receives each raw page as it arrives. Comes from the store, so adapters
# don't know the disk layout.
RawSink = Callable[[RawPage], None]


class Source(Protocol):
    name: str

    def plan(self, searches: Sequence[Search], window: Window) -> FetchPlan: ...

    def fetch(self, plan: FetchPlan, sink: RawSink) -> list[Posting]: ...

    def parse(self, raw: RawPage) -> list[Posting]: ...
