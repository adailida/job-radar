"""Step 2: turn raw pages into postings."""

from collections import Counter
from collections.abc import Mapping

from job_radar.models import AlertCode, Posting, RawPage, SourceCount
from job_radar.sources.base import JobBoardParser
from job_radar.storage.source_count_log import SourceCountLog
from job_radar.storage.warning_log import WarningLog


class ConvertStep:
    """Sends each raw page to the parser for the board it came from, and counts what each gave.

    The count per board, zero for a board that gave nothing, goes to the
    report's header. A board whose pages hold no postings is a warning.
    Stateless: holds only its parsers, where the counts and warnings go, and
    the boards' names for people.
    """

    name = "convert"
    output = Posting

    def __init__(
        self,
        parsers: Mapping[str, JobBoardParser],
        counts: SourceCountLog,
        warnings: WarningLog,
        labels: Mapping[str, str],
    ) -> None:
        """Keep one parser per board, by board name, where counts and warnings go, and names.

        `labels` names each board for people, by its name in the data.
        """
        self._parsers = parsers
        self._counts = counts
        self._warnings = warnings
        self._labels = labels

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
        for source in dict.fromkeys(page.source for page in data):
            if not given[source]:
                label = self._labels.get(source, source)
                self._warnings.warn(AlertCode.SOURCE_EMPTY, f"{label} returned no postings.")
        return postings
