"""Step 1: fetch raw pages from every job board."""

from collections.abc import Sequence
from typing import Never

from job_radar.models import (
    AlertCode,
    Approval,
    PaidFetch,
    RawPage,
    SearchCriteria,
    Spend,
    SpendDecision,
    Window,
)
from job_radar.sources.base import JobBoardSource, PaidSource
from job_radar.storage.spend_log import SpendLog
from job_radar.storage.warning_log import WarningLog
from job_radar.utils.errors import JobRadarError


class NoSourceData(JobRadarError):
    """Every source the run tried failed, so there is nothing to work on."""


class FetchStep:
    """Fetches raw pages for the user's searches from every configured job board.

    A paid board spends at most what its approval allows, and is left out when
    the user chose to skip it; what it spent is recorded, with a warning when
    it used up its monthly budget or has few credits left. A board that fails
    is left out with a warning and the others go on; only when every board it
    tried failed does the step fail. A board that gave nothing is a warning
    too. Stateless: holds only its sources, the searches, the window, the
    approvals, the spend log, where warnings go and the low-credits mark.
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
        warnings: WarningLog,
        low_credits: int,
    ) -> None:
        """Keep the boards to ask, what to ask them for, what paid ones may spend, and the logs.

        `low_credits` is how few credits left after the fetch is worth a warning.
        """
        self._sources = sources
        self._criteria = criteria
        self._window = window
        self._approvals = {approval.source: approval for approval in approvals}
        self._log = log
        self._warnings = warnings
        self._low_credits = low_credits

    def run(self, data: list[Never]) -> list[RawPage]:
        """Fetch from each board in turn. Takes nothing: it is the first step.

        Raises `NoSourceData` when every board it tried failed.
        """
        pages: list[RawPage] = []
        failed: list[tuple[str, str]] = []  # each failed board's name for people, and why
        succeeded = 0
        for source in self._sources:
            approval = self._approvals.get(source.name)
            if approval is not None and approval.decision is SpendDecision.SKIPPED:
                self._log.write(Spend(approval=approval))
                self._warnings.warn(
                    AlertCode.SOURCE_SKIPPED,
                    f"{source.label} skipped by you at the cost check: "
                    "its postings are not in this run.",
                )
                continue
            if approval is not None and approval.decision is SpendDecision.FAILED:
                failed.append((source.label, f"{approval.failure} (at the cost check)"))
                continue
            try:
                got = self._fetch(source, approval)
            except Exception as error:
                failed.append((source.label, JobRadarError.describe(error)))
                continue
            succeeded += 1
            if not got:
                self._warnings.warn(AlertCode.SOURCE_EMPTY, f"{source.label} returned no postings.")
            pages.extend(got)
        if failed and not succeeded:
            raise NoSourceData(
                "No source returned data: "
                + ", ".join(f"{label} failed ({reason})" for label, reason in failed)
            )
        for label, reason in failed:
            self._warnings.warn(
                AlertCode.SOURCE_FAILED,
                f"{label} failed: {reason.rstrip('.')}. Its postings are not in this run.",
            )
        return pages

    def _fetch(self, source: JobBoardSource, approval: Approval | None) -> list[RawPage]:
        """One board's pages; a paid one within its approval, recording what it spent."""
        if approval is None or not isinstance(source, PaidSource):
            return source.fetch(self._criteria, self._window)
        paid = source.fetch_paid(self._criteria, self._window, approval.cap)
        self._log.write(
            Spend(approval=approval, charged=paid.charged, credits_after=paid.credits_left)
        )
        self._credits(source.label, approval, paid)
        return list(paid.pages)

    def _credits(self, label: str, approval: Approval, paid: PaidFetch) -> None:
        """Warn when a paid board used up its monthly budget, or has few credits left."""
        budget = approval.budget_left
        if budget is not None and paid.charged and paid.charged >= budget:
            self._warnings.warn(
                AlertCode.BUDGET_REACHED,
                f"{label} monthly budget reached: this run used {paid.charged} credits, "
                f"and the budget had {budget} left this month.",
            )
        if paid.credits_left < self._low_credits:
            self._warnings.warn(
                AlertCode.CREDITS_LOW,
                f"{label} credits running low: {paid.credits_left} left "
                f"(alerts.low_credits is {self._low_credits}).",
            )
