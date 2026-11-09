from datetime import date

from fakes import FakeHistory, FakePrompter, FixedClock

from job_radar.model import Window
from job_radar.window import WindowPlan, WindowPlanner, WindowReason
from job_radar.window_chooser import WindowChooser

TODAY = date(2026, 11, 5)
PLANNER = WindowPlanner(lookback_days=14)


def ran(day: date) -> Window:
    """The window of a run that ended on that day."""
    return Window(start=date(2026, 9, 1), end=day)


def test_first_run_fetches_the_lookback():
    assert PLANNER.plan(TODAY, None) == WindowPlan(
        window=Window(start=date(2026, 10, 22), end=TODAY), reason=WindowReason.FIRST_RUN
    )


def test_later_run_starts_a_day_before_the_last_runs_last_day():
    plan = PLANNER.plan(TODAY, ran(date(2026, 11, 3)))
    assert plan.window == Window(start=date(2026, 11, 2), end=TODAY)
    assert (plan.reason, plan.last_run) == (WindowReason.SINCE_LAST_RUN, date(2026, 11, 3))


def test_second_run_on_the_same_day_covers_that_day_again():
    plan = PLANNER.plan(TODAY, ran(TODAY))
    assert plan.window == Window(start=date(2026, 11, 4), end=TODAY)


def test_run_never_reaches_further_back_than_the_lookback():
    plan = PLANNER.plan(TODAY, ran(date(2026, 9, 30)))
    assert plan.window == Window(start=date(2026, 10, 22), end=TODAY)
    assert (plan.reason, plan.last_run) == (WindowReason.CAPPED, date(2026, 9, 30))


def test_last_run_right_at_the_lookback_is_not_capped():
    plan = PLANNER.plan(TODAY, ran(date(2026, 10, 23)))
    assert plan.reason is WindowReason.SINCE_LAST_RUN
    assert plan.window.start == date(2026, 10, 22)


def test_last_run_dated_after_today_starts_today():
    plan = PLANNER.plan(TODAY, ran(date(2026, 11, 9)))
    assert plan.window == Window(start=TODAY, end=TODAY)


def chooser(last: Window | None, prompter: FakePrompter) -> WindowChooser:
    return WindowChooser(FakeHistory(last), PLANNER, prompter, FixedClock())


def test_first_run_asks_before_fetching():
    prompter = FakePrompter(True)
    assert chooser(None, prompter).choose().window == Window(start=date(2026, 10, 22), end=TODAY)
    assert prompter.told == ["No earlier runs. Fetching the last 14 days: Oct 22 to Nov 5."]
    assert prompter.asked == ["Continue?"]


def test_saying_no_gives_no_window():
    assert chooser(None, FakePrompter(False)).choose() is None


def test_capped_run_asks_and_says_why():
    prompter = FakePrompter(True)
    chooser(ran(date(2026, 9, 30)), prompter).choose()
    assert prompter.told == [
        "The last run was on Sep 30, more than 14 days ago. "
        "Fetching only the last 14 days: Oct 22 to Nov 5."
    ]
    assert prompter.asked == ["Continue?"]


def test_run_after_a_recent_one_goes_ahead_without_asking():
    prompter = FakePrompter()
    assert chooser(ran(date(2026, 11, 3)), prompter).choose().window == Window(
        start=date(2026, 11, 2), end=TODAY
    )
    assert prompter.told == [
        "The last run was on Nov 3. Fetching Nov 2 to Nov 5, "
        "from the day before it, to catch postings listed late."
    ]
    assert prompter.asked == []


def test_a_capped_run_names_the_days_it_leaves_out():
    plan = PLANNER.plan(TODAY, ran(date(2026, 9, 30)))
    assert plan.not_covered() == Window(start=date(2026, 10, 1), end=date(2026, 10, 21))


def test_a_capped_run_right_after_the_lookback_leaves_nothing_out():
    plan = PLANNER.plan(TODAY, ran(date(2026, 10, 22)))
    assert plan.reason is WindowReason.CAPPED
    assert plan.not_covered() is None


def test_first_and_later_runs_leave_nothing_out():
    assert PLANNER.plan(TODAY, None).not_covered() is None
    assert PLANNER.plan(TODAY, ran(date(2026, 11, 3))).not_covered() is None
