from datetime import date

import pytest
from fakes import FakePrompter, MemorySpendLog, MemoryWarningLog

from job_radar.cost import CostCheck, FileSpendLog
from job_radar.model import (
    Approval,
    PaidFetch,
    RawPage,
    Search,
    SearchCriteria,
    Spend,
    SpendDecision,
    SpendPlan,
    Window,
)
from job_radar.prompter import TerminalPrompter
from job_radar.steps.fetch import FetchStep

WINDOW = Window(start=date(2026, 11, 8), end=date(2026, 11, 9))
CRITERIA = SearchCriteria(searches=(Search(name="s"),))


def plan(estimate=18, left=844, per_run=25, budget=844, estimated=True) -> SpendPlan:
    """A spend plan for JobsPipe."""
    return SpendPlan(
        source="jobspipe",
        estimate=estimate,
        estimated=estimated,
        credits_left=left,
        per_run_max=per_run,
        budget_left=budget,
    )


class Planned:
    """A paid source with a set plan, remembering what it was asked to spend."""

    name = "jobspipe"
    label = "JobsPipe"

    def __init__(self, spend_plan: SpendPlan):
        self._plan, self.caps = spend_plan, []

    def plan(self, criteria, window):
        return self._plan

    def fetch(self, criteria, window):
        return []

    def fetch_paid(self, criteria, window, cap):
        self.caps.append(cap)
        page = RawPage(source="jobspipe", page=1, body="{}")
        return PaidFetch(pages=(page,), charged=cap - 2, credits_left=100)


def check(spend_plan: SpendPlan, *answers: str):
    """The cost check over one source with this plan, and a user giving these answers."""
    prompter = FakePrompter(*answers)
    return CostCheck([Planned(spend_plan)], CRITERIA, prompter).check(WINDOW), prompter


def test_within_every_limit_it_goes_ahead_with_ten_percent_to_spare():
    [approval], prompter = check(plan(estimate=18))
    assert (approval.decision, approval.cap, approval.credits_before) == (
        SpendDecision.AUTO,
        20,
        844,
    )
    assert prompter.asked == []
    assert prompter.told == [
        "jobspipe: about 18 credits for this run "
        "(per-run max 25, budget left 844, credits left 844)."
    ]


@pytest.mark.parametrize(
    ("answer", "decision", "cap"),
    [("g", SpendDecision.APPROVED, 44), ("s", SpendDecision.SKIPPED, 0)],
)
def test_over_the_per_run_max_the_user_chooses(answer, decision, cap):
    [approval], prompter = check(plan(estimate=40), answer)
    assert (approval.decision, approval.cap) == (decision, cap)
    assert prompter.asked == [
        "That's over the per-run max. Go ahead, skip jobspipe this run, or stop?"
    ]


def test_over_a_limit_the_run_shows_the_estimate_both_limits_and_the_credits_left_and_asks():
    # Acceptance (Cost): over the per-run maximum or the monthly budget, the run shows the
    # estimate, both limits and the credits left, and asks: go ahead, skip that source, or stop.
    [approval], prompter = check(plan(estimate=40, budget=30), "g")
    assert prompter.told == [
        "jobspipe: about 40 credits for this run "
        "(per-run max 25, budget left 30, credits left 844)."
    ]
    assert prompter.asked == [
        "That's over the per-run max. Go ahead, skip jobspipe this run, or stop?"
    ]
    assert approval.decision is SpendDecision.APPROVED


def test_over_the_budget_left_the_user_chooses():
    _, prompter = check(plan(estimate=20, budget=10), "s")
    assert prompter.asked == [
        "That's over the budget left. Go ahead, skip jobspipe this run, or stop?"
    ]


def test_stopping_stops_the_run():
    approvals, _ = check(plan(estimate=40), "x")
    assert approvals is None


def test_over_the_credits_left_only_skip_or_stop():
    [approval], prompter = check(plan(estimate=900, per_run=2500, budget=900), "s")
    assert approval.decision is SpendDecision.SKIPPED
    assert prompter.asked == [
        "That's more than the 844 credits left. Skip jobspipe this run, or stop?"
    ]


def test_an_estimate_jobspipe_couldnt_count_says_at_most():
    _, prompter = check(plan(estimate=25, estimated=False))
    assert prompter.told[0].startswith("jobspipe: at most 25 credits")


def test_the_cap_never_passes_the_credits_left():
    [approval], _ = check(plan(estimate=20, left=21, budget=21))
    assert approval.cap == 21


def approval(decision=SpendDecision.AUTO, cap=20) -> Approval:
    """An approval for JobsPipe."""
    return Approval(source="jobspipe", estimate=18, decision=decision, cap=cap, credits_before=844)


def test_the_fetch_spends_within_the_approval_and_records_it():
    paid, log = Planned(plan()), MemorySpendLog()
    pages = FetchStep([paid], CRITERIA, WINDOW, [approval()], log, MemoryWarningLog(), 100).run([])
    assert paid.caps == [20] and len(pages) == 1
    assert log.written == [Spend(approval=approval(), charged=18, credits_after=100)]


def test_a_skipped_source_fetches_nothing_and_is_recorded():
    paid, log = Planned(plan()), MemorySpendLog()
    skipped = approval(SpendDecision.SKIPPED, cap=0)
    assert (
        FetchStep([paid], CRITERIA, WINDOW, [skipped], log, MemoryWarningLog(), 100).run([]) == []
    )
    assert paid.caps == [] and log.written == [Spend(approval=skipped)]


def test_the_spend_log_keeps_one_record_per_source(tmp_path):
    log = FileSpendLog(tmp_path)
    log.write(Spend(approval=approval(), charged=5, credits_after=839))
    log.write(Spend(approval=approval(), charged=18, credits_after=826))
    assert [s.charged for s in log.spends()] == [18]
    assert FileSpendLog(tmp_path / "none").spends() == []


def test_choose_takes_a_letter_enter_or_no_input_for_the_default():
    lines: list[str] = []
    replies = iter(["maybe", "g"])
    terminal = TerminalPrompter(read=lambda q: lines.append(q) or next(replies), write=lines.append)
    assert terminal.choose("Go?", {"g": "go ahead", "s": "skip"}, "s") == "g"
    assert lines == [
        "Go? (g/s, Enter for s) ",
        "Please answer g to go ahead, s to skip.",
        "Go? (g/s, Enter for s) ",
    ]

    def closed(question):
        raise EOFError

    assert (
        TerminalPrompter(read=closed, write=print).choose("Go?", {"g": "go", "s": "skip"}, "s")
        == "s"
    )
