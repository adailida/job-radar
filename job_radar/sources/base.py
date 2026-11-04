"""The interface every job source implements, and the types a source exchanges with a run."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from job_radar.model import Posting, Search, Window


@dataclass(frozen=True)
class FetchPlan:
    """What a source will request in one run: one query per search, limited to the run's dates.

    Made before anything is fetched, so paid sources can be costed and approved first.
    """

    source: str
    window: Window
    queries: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RawPage:
    """One page of a source's response, exactly as received.

    Kept so postings can be parsed again after a parser fix, without fetching
    (or paying) again.
    """

    source: str
    page: int
    body: bytes


SavePage = Callable[[RawPage], None]
"""A function the source calls with each raw page as soon as it arrives.

The run supplies it. The source only hands pages over; where and how they are
kept is not its concern.
"""


class Source(Protocol):
    """A job board or API that postings come from.

    Turns the user's searches into its own queries, fetches the results, and
    converts them into Postings.

    Stateless: holds only its configuration (board, HTTP client, request delay)
    and keeps nothing between calls. The plan is data the caller holds between
    `plan` and `fetch`, so all paid sources can be approved before any fetch.
    """

    name: str

    def plan(self, searches: Sequence[Search], window: Window) -> FetchPlan:
        """Turn the searches and the run's dates into this source's queries. Sends no requests."""
        ...

    def fetch(self, plan: FetchPlan, save_page: SavePage) -> list[Posting]:
        """Run the plan's queries page by page and return every posting found.

        Each raw page goes to `save_page` as it arrives. If any page fails, raises
        instead of returning, so a source's results are complete or absent, never partial.
        """
        ...

    def parse(self, raw: RawPage) -> list[Posting]:
        """Convert one raw page into postings. Sends no requests, so it works on saved pages."""
        ...
