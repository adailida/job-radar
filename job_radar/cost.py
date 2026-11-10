"""Agreeing what paid sources may spend, before anything is fetched."""

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from job_radar.errors import JobRadarError
from job_radar.model import Approval, SearchCriteria, Spend, SpendDecision, SpendPlan, Window
from job_radar.prompter import Prompter
from job_radar.sources.base import PaidSource


class CostCheck:
    """Checks each paid source's estimate against its limits, and asks when one is over.

    Within the per-run max, the budget and the credits left, a source goes
    ahead on its own. Over the per-run max or the budget, the user chooses:
    go ahead, skip the source this run, or stop. Over the credits left, only
    skip or stop: running out mid-fetch would leave it partial. Enter means
    skip, the safe choice. The fetch may then spend the estimate plus 10%, as
    new postings can appear between the count and the fetch. A source whose
    check fails is left out of the run, and the fetch step warns about it.
    Stateless: holds only the paid sources, the searches and who it asks.
    """

    MARGIN = 0.10

    def __init__(
        self, sources: Sequence[PaidSource], criteria: SearchCriteria, prompter: Prompter
    ) -> None:
        """Keep the paid sources, the searches they run, and who to ask."""
        self._sources = sources
        self._criteria = criteria
        self._prompter = prompter

    def check(self, window: Window) -> list[Approval] | None:
        """One approval per paid source, or None if the user chose to stop the run."""
        approvals = []
        for source in self._sources:
            try:
                plan = source.plan(self._criteria, window)
            except Exception as error:
                approvals.append(self._failed(source, error))
                continue
            approval = self._decide(plan)
            if approval is None:
                return None
            approvals.append(approval)
        return approvals

    def _failed(self, source: PaidSource, error: Exception) -> Approval:
        """The approval of a source whose check failed: left out of the run, and why."""
        reason = JobRadarError.describe(error)
        self._prompter.tell(
            f"{source.label}: the cost check failed ({reason}), so it is left out of this run."
        )
        return Approval(
            source=source.name,
            estimate=0,
            decision=SpendDecision.FAILED,
            cap=0,
            credits_before=0,
            failure=reason,
        )

    def _decide(self, plan: SpendPlan) -> Approval | None:
        """The approval for one source's plan, asking the user when a limit is in the way."""
        name = plan.source
        about = "about " if plan.estimated else "at most "
        self._prompter.tell(
            f"{name}: {about}{plan.estimate} credits for this run "
            f"(per-run max {plan.per_run_max}, budget left {plan.budget_left}, "
            f"credits left {plan.credits_left})."
        )
        cap = min(math.ceil(plan.estimate * (1 + self.MARGIN)), plan.credits_left)
        if plan.estimate > plan.credits_left:
            choice = self._prompter.choose(
                f"That's more than the {plan.credits_left} credits left. "
                f"Skip {name} this run, or stop?",
                {"s": "skip", "x": "stop"},
                default="s",
            )
        elif plan.estimate > plan.per_run_max or plan.estimate > plan.budget_left:
            over = "per-run max" if plan.estimate > plan.per_run_max else "budget left"
            choice = self._prompter.choose(
                f"That's over the {over}. Go ahead, skip {name} this run, or stop?",
                {"g": "go ahead", "s": "skip", "x": "stop"},
                default="s",
            )
        else:
            return self._approval(plan, SpendDecision.AUTO, cap)
        if choice == "x":
            return None
        decision = SpendDecision.APPROVED if choice == "g" else SpendDecision.SKIPPED
        return self._approval(plan, decision, cap if choice == "g" else 0)

    @staticmethod
    def _approval(plan: SpendPlan, decision: SpendDecision, cap: int) -> Approval:
        """The approval record for a plan."""
        return Approval(
            source=plan.source,
            estimate=plan.estimate,
            decision=decision,
            cap=cap,
            credits_before=plan.credits_left,
            budget_left=plan.budget_left,
        )


@runtime_checkable
class SpendLog(Protocol):
    """Keeps what each paid source spent in a run (Repository)."""

    def write(self, spend: Spend) -> None:
        """Record one source's spend."""
        ...

    def spends(self) -> list[Spend]:
        """Every source's spend in this run, in the order recorded."""
        ...


class FileSpendLog:
    """Keeps a run's spend in `spend.jsonl` in its run folder, which stays after the run.

    Holds only its folder; the file is the state.
    """

    NAME = "spend.jsonl"

    def __init__(self, folder: Path) -> None:
        """Keep the run folder the file goes in."""
        self._folder = folder

    def write(self, spend: Spend) -> None:
        """Add one source's spend, replacing an earlier record for the same source."""
        kept = [s for s in self.spends() if s.approval.source != spend.approval.source]
        lines = "".join(s.model_dump_json() + "\n" for s in (*kept, spend))
        (self._folder / self.NAME).write_text(lines, encoding="utf-8")

    def spends(self) -> list[Spend]:
        """Every recorded spend; none when nothing paid ran."""
        path = self._folder / self.NAME
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [Spend.model_validate(json.loads(line)) for line in lines if line.strip()]
