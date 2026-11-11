"""Step 1: fetch raw pages from every job board."""

from collections.abc import Sequence
from typing import Never

from job_radar.models import (
    AlertCode,
    Approval,
    PaidFetch,
    RawPage,
    RunWindows,
    SearchCriteria,
    Spend,
    SpendDecision,
)
from job_radar.sources.base import JobBoardSource, PaidSource
from job_radar.storage.checkpoints import CoverageLog
from job_radar.storage.spend_log import SpendLog
from job_radar.storage.warning_log import WarningLog
from job_radar.utils.errors import JobRadarError


class NoSourceData(JobRadarError):
    """Every source the run tried failed, so there is nothing to work on."""


class FetchStep:
    """Fetches raw pages for the user's searches from every configured job board.

    Each board is asked for its own dates. A paid board spends what its
    approval allows, more only if the user agrees during the fetch, and is
    left out when the user chose to skip it; what it spent and any credits
    agreed during the fetch are recorded, with a warning when it used up its
    monthly budget or has few credits left. A board that fails is left out
    with a warning and the others go on; only when every board it tried
    failed does the step fail. A board that gave nothing is a warning too.
    Which boards it covered in full is recorded, so the next run fetches the
    dates of the others again: not one that failed, was skipped, or gave
    nothing although its count found jobs. Stateless: holds only its sources,
    the searches, the windows, the approvals, the logs, where warnings go and
    the low-credits mark.
    """

    name = "fetch"
    output = RawPage

    def __init__(
        self,
        sources: Sequence[JobBoardSource],
        criteria: SearchCriteria,
        windows: RunWindows,
        approvals: Sequence[Approval],
        log: SpendLog,
        warnings: WarningLog,
        low_credits: int,
        coverage: CoverageLog,
    ) -> None:
        """Keep the boards to ask, what to ask them for, what paid ones may spend, and the logs.

        `low_credits` is how few credits left after the fetch is worth a
        warning; `coverage` is where the boards it covered are recorded.
        """
        self._sources = sources
        self._criteria = criteria
        self._windows = windows
        self._approvals = {approval.source: approval for approval in approvals}
        self._log = log
        self._warnings = warnings
        self._low_credits = low_credits
        self._coverage = coverage

    def run(self, data: list[Never]) -> list[RawPage]:
        """Fetch from each board in turn. Takes nothing: it is the first step.

        Raises `NoSourceData` when every board it tried failed.
        """
        pages: list[RawPage] = []
        failed: list[tuple[str, str]] = []  # each failed board's name for people, and why
        succeeded = 0
        covered = {source.name: False for source in self._sources}
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
            covered[source.name] = bool(got) or self._empty(source, approval)
            pages.extend(got)
        if failed and not succeeded:
            raise NoSourceData(
                "No source returned data: "
                + ", ".join(f"{label} failed ({reason})" for label, reason in failed)
            )
        self._coverage.record(covered)
        for label, reason in failed:
            self._warnings.warn(
                AlertCode.SOURCE_FAILED,
                f"{label} failed: {reason.rstrip('.')}. Its postings are not in this run.",
            )
        return pages

    def _empty(self, source: JobBoardSource, approval: Approval | None) -> bool:
        """Warn that a board gave nothing; whether that still covers its dates.

        It does, unless the board is paid and its count found jobs or couldn't
        count: then the search likely failed without saying so, and the next run
        fetches those dates again (an empty fetch costs nothing).
        """
        if approval is not None and approval.estimated and approval.estimate > 0:
            self._warnings.warn(
                AlertCode.SOURCE_EMPTY,
                f"{source.label} returned no postings, though its count found "
                f"{approval.estimate:,}: the next run fetches these dates again.",
            )
            return False
        if approval is not None and not approval.estimated:
            self._warnings.warn(
                AlertCode.SOURCE_EMPTY,
                f"{source.label} returned no postings and couldn't count them first, so its "
                "search may have timed out: the next run fetches these dates again.",
            )
            return False
        self._warnings.warn(AlertCode.SOURCE_EMPTY, f"{source.label} returned no postings.")
        return True

    def _fetch(self, source: JobBoardSource, approval: Approval | None) -> list[RawPage]:
        """One board's pages for its own dates; a paid one within its approval, recording spend."""
        window = self._windows.of(source.name)
        if approval is None or not isinstance(source, PaidSource):
            return source.fetch(self._criteria, window)
        paid = source.fetch_paid(self._criteria, window, approval.cap, approval.counts)
        self._log.write(
            Spend(
                approval=approval,
                charged=paid.charged,
                credits_after=paid.credits_left,
                extra_approved=paid.extra_approved,
            )
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
