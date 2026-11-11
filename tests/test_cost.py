from datetime import date

import pytest
from fakes import FakePrompter, MemoryCoverage, MemorySpendLog, MemoryWarningLog

from job_radar.app.cost_check import CostCheck
from job_radar.models import (
    Approval,
    PaidFetch,
    RawPage,
    RunWindows,
    Search,
    SearchCriteria,
    SourceWindow,
    Spend,
    SpendDecision,
    SpendPlan,
    Window,
    WindowReason,
)
from job_radar.pipeline.steps.fetch import FetchStep, NoSourceData
from job_radar.storage.spend_log import FileSpendLog
from job_radar.utils.prompter import TerminalPrompter

WINDOW = Window(start=date(2026, 11, 8), end=date(2026, 11, 9))
WINDOWS = RunWindows(window=WINDOW)
CRITERIA = SearchCriteria(searches=(Search(name="s"),))


def plan(estimate=18, left=844, ask_above=25, budget=844, estimated=True) -> SpendPlan:
    """A spend plan for JobsPipe."""
    return SpendPlan(
        source="jobspipe",
        estimate=estimate,
        estimated=estimated,
        credits_left=left,
        ask_above=ask_above,
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
    return CostCheck([Planned(spend_plan)], CRITERIA, prompter).check(WINDOWS), prompter


def test_within_every_limit_it_goes_ahead_with_ten_percent_to_spare():
    [approval], prompter = check(plan(estimate=18))
    assert (approval.decision, approval.cap, approval.credits_before) == (
        SpendDecision.AUTO,
        20,
        844,
    )
    assert prompter.asked == []
    assert prompter.told == [
        "jobspipe: about 18 credits for this run (ask above 25, budget left 844, credits left 844)."
    ]


@pytest.mark.parametrize(
    ("answer", "decision", "cap"),
    [("g", SpendDecision.APPROVED, 44), ("s", SpendDecision.SKIPPED, 0)],
)
def test_over_the_ask_above_limit_the_user_chooses(answer, decision, cap):
    [approval], prompter = check(plan(estimate=40), answer)
    assert (approval.decision, approval.cap) == (decision, cap)
    assert prompter.asked == [
        "That's over the ask-above limit. Go ahead, skip jobspipe this run, or stop?"
    ]


def test_over_a_limit_the_run_shows_the_estimate_both_limits_and_the_credits_left_and_asks():
    # Acceptance (Cost): over the per-run ask-above limit or the monthly budget, the run shows the
    # estimate, both limits and the credits left, and asks: go ahead, skip that source, or stop.
    [approval], prompter = check(plan(estimate=40, budget=30), "g")
    assert prompter.told == [
        "jobspipe: about 40 credits for this run (ask above 25, budget left 30, credits left 844)."
    ]
    assert prompter.asked == [
        "That's over the ask-above limit. Go ahead, skip jobspipe this run, or stop?"
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
    [approval], prompter = check(plan(estimate=900, ask_above=2500, budget=900), "s")
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


def fetch(sources, approvals, log, coverage=None, windows=WINDOWS) -> FetchStep:
    """A fetch step over these sources and approvals, warnings kept in memory."""
    return FetchStep(
        sources,
        CRITERIA,
        windows,
        approvals,
        log,
        MemoryWarningLog(),
        100,
        coverage if coverage is not None else MemoryCoverage(),
    )


def test_the_fetch_spends_within_the_approval_and_records_it():
    paid, log = Planned(plan()), MemorySpendLog()
    pages = fetch([paid], [approval()], log).run([])
    assert paid.caps == [20] and len(pages) == 1
    assert log.written == [Spend(approval=approval(), charged=18, credits_after=100)]


class KeptGoing(Planned):
    """A paid source where the user agreed to more credits during the fetch."""

    def fetch_paid(self, criteria, window, cap):
        page = RawPage(source="jobspipe", page=1, body="{}")
        return PaidFetch(pages=(page,), charged=38, credits_left=806, extra_approved=20)


def test_credits_agreed_during_the_fetch_are_recorded_with_what_it_charged():
    log = MemorySpendLog()
    fetch([KeptGoing(plan())], [approval()], log).run([])
    assert log.written == [
        Spend(approval=approval(), charged=38, credits_after=806, extra_approved=20)
    ]


def test_a_skipped_source_fetches_nothing_and_is_recorded():
    paid, log = Planned(plan()), MemorySpendLog()
    skipped = approval(SpendDecision.SKIPPED, cap=0)
    assert fetch([paid], [skipped], log).run([]) == []
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


class Free:
    """A free board that remembers the window it was asked for; gives pages, nothing, or fails."""

    def __init__(self, name="getro", pages=1, error=None):
        self.name, self.label, self._pages, self._error = name, "Fast Forward", pages, error
        self.windows = []

    def fetch(self, criteria, window):
        self.windows.append(window)
        if self._error:
            raise self._error
        return [RawPage(source=self.name, page=n, body="") for n in range(1, self._pages + 1)]


class Empty(Planned):
    """A paid source that comes back with nothing, as a phrase search that timed out."""

    def fetch_paid(self, criteria, window, cap):
        return PaidFetch(pages=(), charged=0, credits_left=844)


class Remembering(Planned):
    """A paid source that remembers the window each call was for."""

    def __init__(self, spend_plan: SpendPlan):
        super().__init__(spend_plan)
        self.windows = []

    def plan(self, criteria, window):
        self.windows.append(window)
        return super().plan(criteria, window)

    def fetch_paid(self, criteria, window, cap):
        self.windows.append(window)
        return super().fetch_paid(criteria, window, cap)


def covered(sources, approvals) -> dict[str, bool] | None:
    """What a fetch over these sources and approvals recorded as covered."""
    coverage = MemoryCoverage()
    fetch(sources, approvals, MemorySpendLog(), coverage).run([])
    return coverage.covered


def test_a_source_fetched_in_full_is_covered():
    assert covered([Free(), Planned(plan())], [approval()]) == {"getro": True, "jobspipe": True}


def test_a_source_that_failed_is_not_covered():
    down = Free("jobspipe", error=RuntimeError("HTTP 503"))
    assert covered([Free(), down], []) == {"getro": True, "jobspipe": False}


def test_a_source_skipped_or_failed_at_the_cost_check_is_not_covered():
    skipped = approval(SpendDecision.SKIPPED, cap=0)
    assert covered([Free(), Planned(plan())], [skipped]) == {"getro": True, "jobspipe": False}
    failed = approval(SpendDecision.FAILED, cap=0).model_copy(update={"failure": "HTTP 503"})
    assert covered([Free(), Planned(plan())], [failed]) == {"getro": True, "jobspipe": False}


def test_a_source_empty_although_its_count_found_jobs_is_not_covered_and_says_so():
    coverage, warnings = MemoryCoverage(), MemoryWarningLog()
    step = FetchStep(
        [Free(), Empty(plan())],
        CRITERIA,
        WINDOWS,
        [approval()],
        MemorySpendLog(),
        warnings,
        100,
        coverage,
    )
    step.run([])
    assert coverage.covered == {"getro": True, "jobspipe": False}
    assert warnings.messages() == [
        "JobsPipe returned no postings, though its count found 18: "
        "the next run fetches these dates again."
    ]


def test_a_paid_source_empty_that_couldnt_count_is_not_covered_and_says_so():
    uncounted = approval().model_copy(update={"estimated": False, "estimate": 25})
    coverage, warnings = MemoryCoverage(), MemoryWarningLog()
    step = FetchStep(
        [Free(), Empty(plan())],
        CRITERIA,
        WINDOWS,
        [uncounted],
        MemorySpendLog(),
        warnings,
        100,
        coverage,
    )
    step.run([])
    assert coverage.covered == {"getro": True, "jobspipe": False}
    assert warnings.messages() == [
        "JobsPipe returned no postings and couldn't count them first, so its search may "
        "have timed out: the next run fetches these dates again."
    ]


def test_a_source_genuinely_empty_is_covered():
    nothing = approval().model_copy(update={"estimate": 0})
    assert covered([Free(), Empty(plan())], [nothing]) == {"getro": True, "jobspipe": True}
    assert covered([Free(pages=0), Planned(plan())], [approval()]) == {
        "getro": True,
        "jobspipe": True,
    }


def test_a_fetch_where_every_source_failed_records_nothing():
    coverage = MemoryCoverage()
    with pytest.raises(NoSourceData):
        fetch([Free(error=RuntimeError("down"))], [], MemorySpendLog(), coverage).run([])
    assert coverage.covered is None


EARLY = Window(start=date(2026, 10, 28), end=date(2026, 11, 9))
APART = RunWindows.spanning(
    [
        SourceWindow(source="getro", window=WINDOW, reason=WindowReason.SINCE_LAST_RUN),
        SourceWindow(source="jobspipe", window=EARLY, reason=WindowReason.CATCHING_UP),
    ]
)


def test_the_fetch_asks_each_source_for_its_own_window():
    getro, jobspipe = Free(), Remembering(plan())
    fetch([getro, jobspipe], [approval()], MemorySpendLog(), windows=APART).run([])
    assert (getro.windows, jobspipe.windows) == ([WINDOW], [EARLY])


def test_the_cost_check_plans_each_source_for_its_own_window():
    jobspipe = Remembering(plan())
    CostCheck([jobspipe], CRITERIA, FakePrompter()).check(APART)
    assert jobspipe.windows == [EARLY]


def test_the_approval_keeps_whether_the_estimate_was_counted():
    [counted], _ = check(plan(estimated=True))
    [guessed], _ = check(plan(estimate=25, estimated=False))
    assert (counted.estimated, guessed.estimated) == (True, False)
