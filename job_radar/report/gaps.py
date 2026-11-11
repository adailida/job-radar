"""Experience to gain: what employers ask for, compared with the user's CV."""

import hashlib
from typing import Protocol, runtime_checkable

from job_radar.llm.gap_judge import BadGaps, GapJudge
from job_radar.llm.llm import LlmError, UsageLimit
from job_radar.models import (
    AlertCode,
    AskRow,
    Asks,
    CandidateProfile,
    GapJudgment,
    GapRow,
    Gaps,
    GapSkip,
    GapStatus,
)
from job_radar.report.asks import RequirementNames
from job_radar.storage.gap_cache import GapCache, RequirementKey
from job_radar.storage.warning_log import WarningLog


class GapBuilder:
    """Puts the experience to gain section together from the requirements and their judgments.

    Gaps (missing or partly) come first, most asked first, then the covered
    ones. Only the most asked gaps, up to a set number, show how to gain
    them. Requirements with no judgment are left out and counted. Stateless:
    holds only how names are put in one form and how many gaps show a
    suggestion.
    """

    def __init__(self, names: RequirementNames, suggestions: int) -> None:
        """Keep how names are put in one form, and how many gaps show a suggestion."""
        self._names = names
        self._suggestions = suggestions

    def key(self, row: AskRow) -> RequirementKey:
        """The requirement as counted: its type and its name in one form."""
        return (row.type, self._names.key(row.name))

    def ranked(self, rows: tuple[AskRow, ...]) -> list[AskRow]:
        """The requirements most asked first; on a tie, by name."""
        return sorted(rows, key=lambda row: (-row.share, row.name.casefold()))

    def build(
        self,
        rows: list[AskRow],
        judged: dict[RequirementKey, GapJudgment],
        skipped: GapSkip | None,
    ) -> Gaps:
        """The section: each judged requirement with its status, gaps first, most asked first."""
        found = [
            (row, judged[self.key(row)])
            for row in self.ranked(tuple(rows))
            if self.key(row) in judged
        ]
        gaps = [(r, j) for r, j in found if j.status is not GapStatus.COVERED]
        covered = [(r, j) for r, j in found if j.status is GapStatus.COVERED]
        built = [
            GapRow(
                requirement=row,
                status=judgment.status,
                reason=judgment.reason,
                suggestion=judgment.suggestion if rank < self._suggestions else None,
            )
            for rank, (row, judgment) in enumerate(gaps)
        ]
        built += [
            GapRow(requirement=row, status=judgment.status, reason=judgment.reason, suggestion=None)
            for row, judgment in covered
        ]
        return Gaps(
            rows=tuple(built),
            skipped=skipped,
            not_compared=len(rows) - len(found),
        )


@runtime_checkable
class GapSource(Protocol):
    """Gives the report its experience to gain section."""

    def gaps(self, asks: Asks) -> Gaps:
        """The section, for the requirements in what employers ask for."""
        ...


class CvGaps:
    """Compares what employers ask for with the user's CV, judging each requirement once per CV.

    Judgments are kept by the CV's content hash and the requirement, so only
    requirements new to the list cost a call, and none new means no call. When
    the call fails or the usage limit is reached, the run goes on with a
    warning: the section shows what was judged before and says the rest
    weren't compared. Stateless: holds only the profile, the judge, the
    cache, the builder and where warnings go; the cache keeps the judgments.
    """

    def __init__(
        self,
        profile: CandidateProfile,
        judge: GapJudge,
        cache: GapCache,
        builder: GapBuilder,
        warnings: WarningLog,
    ) -> None:
        """Keep the profile, who judges, where judgments are kept, the builder, the log."""
        self._profile = profile
        self._judge = judge
        self._cache = cache
        self._builder = builder
        self._warnings = warnings

    def gaps(self, asks: Asks) -> Gaps:
        """The section: requirements judged before, plus the new ones judged now in one call."""
        rows = self._builder.ranked(asks.rows)
        if not rows:
            return Gaps(rows=())
        cv = hashlib.sha256(self._profile.cv.encode("utf-8")).hexdigest()
        judged = self._cache.judged(cv)
        new = [row for row in rows if self._builder.key(row) not in judged]
        skipped = None
        if new:
            try:
                found = self._judge.judge(new, self._profile)
            except UsageLimit:
                skipped = GapSkip.USAGE_LIMIT
                self._warn(len(new), "the LLM's usage limit is reached")
            except (BadGaps, LlmError):
                skipped = GapSkip.FAILED
                self._warn(len(new), "the LLM gave no usable answer")
            else:
                fresh = {self._builder.key(row): one for row, one in zip(new, found, strict=True)}
                self._cache.add(cv, fresh)
                judged = judged | fresh
        return self._builder.build(rows, judged, skipped)

    def _warn(self, count: int, why: str) -> None:
        """Warn that some requirements weren't compared with the CV this run, and why."""
        some = "1 requirement wasn't" if count == 1 else f"{count} requirements weren't"
        self._warnings.warn(
            AlertCode.GAPS_SKIPPED,
            f"Experience to gain: {some} compared with your CV ({why}). The next run asks again.",
        )
