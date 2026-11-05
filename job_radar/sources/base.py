"""The two interfaces every job board brings: one to fetch, one to parse."""

from typing import Protocol, runtime_checkable

from job_radar.model import Posting, RawPage, Search, Window


@runtime_checkable
class JobBoardSource(Protocol):
    """Talks to one job board's API (Adapter).

    Stateless: holds only its configuration and HTTP client.
    """

    name: str  # "getro", "jobspipe"; also the name of its parser's source

    def fetch(self, search: Search, window: Window) -> list[RawPage]:
        """Query the board for the search and window, page by page, unparsed."""
        ...


@runtime_checkable
class JobBoardParser(Protocol):
    """Turns one job board's records into postings (Adapter). Stateless."""

    source: str  # the board whose pages it parses

    def parse(self, page: RawPage) -> list[Posting]:
        """Convert one raw page into postings."""
        ...
