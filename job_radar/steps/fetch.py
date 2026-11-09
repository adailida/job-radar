"""Step 1: fetch raw pages from every job board."""

from collections.abc import Sequence
from typing import Never

from job_radar.model import RawPage, SearchCriteria, Window
from job_radar.sources.base import JobBoardSource


class FetchStep:
    """Fetches raw pages for the user's searches from every configured job board.

    Stateless: holds only its sources, the searches and the window.
    """

    name = "fetch"
    output = RawPage

    def __init__(
        self, sources: Sequence[JobBoardSource], criteria: SearchCriteria, window: Window
    ) -> None:
        """Keep the boards to ask, and what to ask them for."""
        self._sources = sources
        self._criteria = criteria
        self._window = window

    def run(self, data: list[Never]) -> list[RawPage]:
        """Fetch from each board in turn. Takes nothing: it is the first step."""
        return [
            page for source in self._sources for page in source.fetch(self._criteria, self._window)
        ]
