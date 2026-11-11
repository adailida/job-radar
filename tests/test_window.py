from datetime import date

from fakes import FakeHistory, FakePrompter, FixedClock

from job_radar.app.window import WindowChooser, WindowPlan, WindowPlanner, WindowReason
from job_radar.models import Window

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
    return WindowChooser(FakeHistory(last), PLANNER, prompter, FixedClock(), {"demo": "Demo board"})


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


def test_a_source_the_last_run_missed_catches_up_from_where_it_was_covered():
    plan = PLANNER.plan(TODAY, ran(date(2026, 11, 1)), newest=date(2026, 11, 3))
    assert plan.window == Window(start=date(2026, 10, 31), end=TODAY)
    assert (plan.reason, plan.last_run) == (WindowReason.CATCHING_UP, date(2026, 11, 1))


def test_a_source_the_last_run_covered_picks_up_after_it():
    plan = PLANNER.plan(TODAY, ran(date(2026, 11, 3)), newest=date(2026, 11, 3))
    assert plan.reason is WindowReason.SINCE_LAST_RUN


def test_catching_up_never_reaches_further_back_than_the_lookback():
    plan = PLANNER.plan(TODAY, ran(date(2026, 9, 30)), newest=date(2026, 11, 3))
    assert plan.window == Window(start=date(2026, 10, 22), end=TODAY)
    assert plan.reason is WindowReason.CAPPED
    assert plan.not_covered() == Window(start=date(2026, 10, 1), end=date(2026, 10, 21))


SOURCES = {"getro": "Fast Forward", "jobspipe": "JobsPipe"}


def sources_chooser(covered: dict, prompter: FakePrompter) -> WindowChooser:
    """A chooser over two sources, the last run ending Nov 3, each last covered as given."""
    history = FakeHistory(ran(date(2026, 11, 3)), covered)
    return WindowChooser(history, PLANNER, prompter, FixedClock(), SOURCES)


def test_sources_covered_by_the_last_run_share_one_window_said_once():
    prompter = FakePrompter()
    last = ran(date(2026, 11, 3))
    windows = sources_chooser({"getro": last, "jobspipe": last}, prompter).choose()
    assert windows.window == Window(start=date(2026, 11, 2), end=TODAY)
    assert [s.source for s in windows.sources] == ["getro", "jobspipe"]
    assert not windows.differ()
    assert prompter.told == [
        "The last run was on Nov 3. Fetching Nov 2 to Nov 5, "
        "from the day before it, to catch postings listed late."
    ]
    assert prompter.asked == []


def test_each_source_gets_its_own_window_from_where_it_was_last_covered():
    prompter = FakePrompter()
    covered = {"getro": ran(date(2026, 11, 3)), "jobspipe": ran(date(2026, 10, 28))}
    windows = sources_chooser(covered, prompter).choose()
    assert windows.of("getro") == Window(start=date(2026, 11, 2), end=TODAY)
    assert windows.of("jobspipe") == Window(start=date(2026, 10, 27), end=TODAY)
    assert windows.window == Window(start=date(2026, 10, 27), end=TODAY)
    assert [s.reason for s in windows.sources] == [
        WindowReason.SINCE_LAST_RUN,
        WindowReason.CATCHING_UP,
    ]
    assert windows.differ()
    assert prompter.told == [
        "Fetching Oct 27 to Nov 5, each source on its own:",
        "- Fast Forward: Nov 2 to Nov 5, from the day before the last run on Nov 3.",
        "- JobsPipe: Oct 27 to Nov 5, catching up (not covered in the last run; "
        "last covered on Oct 28).",
    ]
    assert prompter.asked == []


def test_a_source_never_covered_reaches_back_the_lookback_and_asks_first():
    prompter = FakePrompter(True)
    windows = sources_chooser(
        {"getro": ran(date(2026, 11, 3)), "jobspipe": None}, prompter
    ).choose()
    assert windows.of("jobspipe") == Window(start=date(2026, 10, 22), end=TODAY)
    assert windows.sources[1].reason is WindowReason.FIRST_RUN
    assert prompter.told[-1] == (
        "- JobsPipe: Oct 22 to Nov 5, the last 14 days (not covered by any earlier run)."
    )
    assert prompter.asked == ["Continue?"]


def test_a_source_last_covered_before_the_lookback_says_which_days_it_leaves_out():
    prompter = FakePrompter(True)
    covered = {"getro": ran(date(2026, 11, 3)), "jobspipe": ran(date(2026, 9, 30))}
    windows = sources_chooser(covered, prompter).choose()
    [_, jobspipe] = windows.sources
    assert jobspipe.reason is WindowReason.CAPPED
    assert jobspipe.not_covered == Window(start=date(2026, 10, 1), end=date(2026, 10, 21))
    assert windows.not_covered is None  # not shared by every source
    assert prompter.told[-1] == (
        "- JobsPipe: Oct 22 to Nov 5, only the last 14 days "
        "(last covered on Sep 30, more than 14 days ago)."
    )
    assert prompter.asked == ["Continue?"]


def test_saying_no_to_a_source_catching_up_from_the_lookback_gives_no_windows():
    prompter = FakePrompter(False)
    covered = {"getro": ran(date(2026, 11, 3)), "jobspipe": None}
    assert sources_chooser(covered, prompter).choose() is None
