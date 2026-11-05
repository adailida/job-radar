"""Step 2: turn raw pages into postings."""

from collections.abc import Mapping

from job_radar.model import Posting, RawPage
from job_radar.sources.base import JobBoardParser


class ConvertStep:
    """Sends each raw page to the parser for the board it came from.

    Stateless: holds only its parsers.
    """

    name = "convert"
    output = Posting

    def __init__(self, parsers: Mapping[str, JobBoardParser]) -> None:
        """Keep one parser per board, by board name."""
        self._parsers = parsers

    def run(self, data: list[RawPage]) -> list[Posting]:
        """Parse every page into postings."""
        # TODO(task 5): pick the parser by page.source.
        raise NotImplementedError
