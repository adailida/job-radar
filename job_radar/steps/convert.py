"""Step 2: turn raw pages into postings."""

from collections import Counter
from collections.abc import Mapping

from job_radar.model import Posting, RawPage, SourceCount
from job_radar.source_counts import SourceCountLog
from job_radar.sources.base import JobBoardParser


class ConvertStep:
    """Sends each raw page to the parser for the board it came from, and counts what each gave.

    The count per board, zero for a board that gave nothing, goes to the
    report's header. Stateless: holds only its parsers and where the counts go.
    """

    name = "convert"
    output = Posting

    def __init__(self, parsers: Mapping[str, JobBoardParser], counts: SourceCountLog) -> None:
        """Keep one parser per board, by board name, and where the counts are recorded."""
        self._parsers = parsers
        self._counts = counts

    def run(self, data: list[RawPage]) -> list[Posting]:
        """Parse every page into postings. A page from a board with no parser is an error."""
        postings: list[Posting] = []
        for page in data:
            parser = self._parsers.get(page.source)
            if parser is None:
                raise ValueError(f"no parser for source '{page.source}'")
            postings.extend(parser.parse(page))
        given = Counter(posting.source for posting in postings)
        self._counts.write(
            [SourceCount(source=source, postings=given[source]) for source in self._parsers]
        )
        return postings
