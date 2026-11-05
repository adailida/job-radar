"""Fast Forward's job board, hosted on Getro."""

import httpx

from job_radar.model import Posting, RawPage, Search, Window


class GetroSource:
    """Queries a Getro-hosted job board's search API.

    Stateless: holds only the board name and its HTTP client.
    """

    name = "getro"

    def __init__(self, board: str, http: httpx.Client) -> None:
        """Keep the board to query and the client to query it with."""
        self._board = board
        self._http = http

    def fetch(self, search: Search, window: Window) -> list[RawPage]:
        """Query the board for the search and window, page by page."""
        # TODO(task 5): find the search API; page through it with a delay and retries.
        raise NotImplementedError


class GetroParser:
    """Turns Getro search results into postings. Stateless."""

    source = "getro"

    def parse(self, page: RawPage) -> list[Posting]:
        """Convert one page of Getro results into postings."""
        # TODO(task 5): map Getro records to Posting.
        raise NotImplementedError
