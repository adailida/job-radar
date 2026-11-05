"""Step 1: fetch raw pages from every job board."""

from collections.abc import Sequence
from typing import Never

from job_radar.model import RawPage, Search, Window
from job_radar.sources.base import JobBoardSource


class FetchStep:
    """Fetches raw pages for the search from every configured job board.

    Stateless: holds only its sources, search and window.
    """

    name = "fetch"
    output = RawPage

    def __init__(self, sources: Sequence[JobBoardSource], search: Search, window: Window) -> None:
        """Keep the boards to ask, and what to ask them for."""
        self._sources = sources
        self._search = search
        self._window = window

    def run(self, data: list[Never]) -> list[RawPage]:
        """Fetch from each board in turn. Takes nothing: it is the first step."""
        return [
            page for source in self._sources for page in source.fetch(self._search, self._window)
        ]
