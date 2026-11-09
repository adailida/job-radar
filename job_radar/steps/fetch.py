"""Step 1: fetch raw pages from every job board."""

from collections.abc import Sequence
from typing import Never

from job_radar.cost import SpendLog
from job_radar.model import Approval, RawPage, SearchCriteria, Spend, SpendDecision, Window
from job_radar.sources.base import JobBoardSource, PaidSource


class FetchStep:
    """Fetches raw pages for the user's searches from every configured job board.

    A paid board spends at most what its approval allows, and is left out when
    the user chose to skip it; what it spent is recorded. Stateless: holds only
    its sources, the searches, the window, the approvals and the spend log.
    """

    name = "fetch"
    output = RawPage

    def __init__(
        self,
        sources: Sequence[JobBoardSource],
        criteria: SearchCriteria,
        window: Window,
        approvals: Sequence[Approval],
        log: SpendLog,
    ) -> None:
        """Keep the boards to ask, what to ask them for, what paid ones may spend, and the log."""
        self._sources = sources
        self._criteria = criteria
        self._window = window
        self._approvals = {approval.source: approval for approval in approvals}
        self._log = log

    def run(self, data: list[Never]) -> list[RawPage]:
        """Fetch from each board in turn. Takes nothing: it is the first step."""
        pages: list[RawPage] = []
        for source in self._sources:
            approval = self._approvals.get(source.name)
            if approval is None or not isinstance(source, PaidSource):
                pages.extend(source.fetch(self._criteria, self._window))
            elif approval.decision is SpendDecision.SKIPPED:
                self._log.write(Spend(approval=approval))
            else:
                paid = source.fetch_paid(self._criteria, self._window, approval.cap)
                self._log.write(
                    Spend(approval=approval, charged=paid.charged, credits_after=paid.credits_left)
                )
                pages.extend(paid.pages)
        return pages
