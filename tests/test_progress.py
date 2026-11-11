import io
from datetime import date

import httpx
from fakes import (
    EXAMPLE,
    REPORT,
    WINDOW,
    FakePrompter,
    FakeStep,
    FixedClock,
    RecordingProgress,
    StepClock,
    job,
    posting,
)
from test_classify import DOMAINS, JOB_TYPES, LabellingLlm, described
from test_extract import ReadingLlm
from test_gaps import PROFILE as GAP_PROFILE
from test_gaps import SetLlm, ask, entry
from test_gaps import answer as gap_answer
from test_ranking import PROFILE as RANK_PROFILE
from test_ranking import FakeLlm, jobs

from job_radar.app.app_factory import AppFactory
from job_radar.app.run_banner import RunBanner
from job_radar.cli import Cli
from job_radar.config.settings import SettingsFile
from job_radar.llm.classifier import LlmClassifier
from job_radar.llm.extractor import LlmExtractor
from job_radar.llm.gap_judge import LlmGapJudge
from job_radar.llm.job_ranker import LlmRanker
from job_radar.models import RunWindows, SourceWindow, Window, WindowReason
from job_radar.pipeline.pipeline import Pipeline
from job_radar.pipeline.steps.describe import DescribeStep
from job_radar.sources.board_client import BoardClient
from job_radar.sources.getro import GetroSource
from job_radar.sources.jobspipe import JobsPipeSource
from job_radar.storage.checkpoints import FileCheckpoints
from job_radar.storage.error_log import FileErrorLog
from job_radar.utils.progress import LineProgress, NoProgress, TerminalProgress
from job_radar.utils.prompter import TerminalPrompter
from job_radar.utils.terminal import Terminal

CLEAR = Terminal.CLEAR


def shown(tty: bool, **kw):
    """A terminal over a string, a stepping clock, and the progress for that kind of output."""
    out, clock = io.StringIO(), StepClock()
    terminal = Terminal(out, tty=tty, read=lambda prompt: "y", width=lambda: 200)
    if tty:
        progress = TerminalProgress(terminal, clock)
    else:
        progress = LineProgress(terminal, clock, **kw)
    return terminal, progress, clock, out


# --- step lines ---


def test_a_finished_step_has_a_numbered_line_with_what_it_gave_and_how_long():
    _, progress, clock, out = shown(False)
    progress.begin(2, 13, "convert")
    clock.advance(0.1)
    progress.done("470 jobs")
    assert out.getvalue() == "[ 2/13] convert         done: 470 jobs (0.1s)\n"


def test_long_steps_show_minutes_and_underscores_become_spaces():
    _, progress, clock, out = shown(False)
    progress.begin(4, 13, "new_jobs_filter")
    clock.advance(65)
    progress.done("3 jobs")
    assert out.getvalue() == "[ 4/13] new jobs filter done: 3 jobs (1m 05s)\n"


def test_a_step_saved_by_an_earlier_attempt_says_so():
    _, progress, _, out = shown(False)
    progress.skipped(1, 13, "fetch")
    assert out.getvalue() == "[ 1/13] fetch           saved earlier\n"


def test_a_failed_step_ends_its_line_as_failed():
    _, progress, clock, out = shown(False)
    progress.begin(3, 13, "dedupe")
    clock.advance(0.4)
    progress.failed()
    assert out.getvalue() == "[ 3/13] dedupe          failed (0.4s)\n"


# --- in place vs lines ---


def test_on_a_terminal_the_current_line_updates_in_place_then_settles():
    _, progress, clock, out = shown(True)
    progress.begin(7, 13, "describe")
    progress.detail("description 1 of 2")
    progress.detail("description 2 of 2")
    clock.advance(2)
    progress.done("2 jobs")
    live = "[ 7/13] describe        "
    assert out.getvalue() == (
        f"{CLEAR}{live}running"
        f"{CLEAR}{CLEAR}{live}description 1 of 2"
        f"{CLEAR}{CLEAR}{live}description 2 of 2"
        f"{CLEAR}{live}done: 2 jobs (2.0s)\n"
    )


def test_off_a_terminal_there_are_no_control_characters_at_all():
    _, progress, clock, out = shown(False)
    progress.begin(1, 2, "fetch")
    progress.detail("page 1")
    clock.advance(10)
    progress.detail("page 2")
    progress.done("5 pages")
    assert "\r" not in out.getvalue() and "\x1b" not in out.getvalue()


def test_lines_are_throttled_but_the_first_update_and_the_done_line_always_show():
    _, progress, clock, out = shown(False, interval=5)
    progress.begin(1, 2, "describe")
    for n in range(1, 13):
        progress.detail(f"{n} of 12")
        clock.advance(1)
    progress.done("12 jobs")
    lines = out.getvalue().splitlines()
    assert [line.split("describe")[1].strip() for line in lines] == [
        "1 of 12",
        "6 of 12",
        "11 of 12",
        "done: 12 jobs (12.0s)",
    ]


def test_each_step_starts_its_throttle_again():
    _, progress, _, out = shown(False, interval=5)
    progress.begin(1, 2, "fetch")
    progress.detail("a")
    progress.begin(2, 2, "describe")
    progress.detail("b")
    assert len(out.getvalue().splitlines()) == 2


def test_no_progress_shows_nothing():
    progress = NoProgress()
    progress.note("x")
    progress.begin(1, 1, "a")
    progress.detail("b")
    progress.done("c")
    progress.skipped(1, 1, "a")
    progress.failed()


# --- prompts and messages ---


def test_a_prompt_during_a_step_clears_the_live_line_and_brings_it_back():
    seen = []
    out = io.StringIO()
    terminal = Terminal(
        out, tty=True, read=lambda p: seen.append(out.getvalue()) or "n", width=lambda: 200
    )
    progress = TerminalProgress(terminal, StepClock())
    prompter = TerminalPrompter(terminal.read, terminal.write)
    progress.begin(1, 2, "fetch")
    progress.detail("JobsPipe nyc, day 3 of 9")
    prompter.confirm("Keep going?", default=False)
    assert seen[0].endswith(CLEAR)  # the line is gone while the question waits
    assert out.getvalue().endswith(f"{CLEAR}[1/2] fetch           JobsPipe nyc, day 3 of 9")
    prompter.tell("A warning.")
    assert f"{CLEAR}A warning.\n{CLEAR}[1/2] fetch" in out.getvalue()
    progress.done("4 pages")
    assert out.getvalue().endswith("done: 4 pages (0.0s)\n")


def test_in_line_mode_prompts_and_messages_are_plain_lines():
    terminal, progress, _, out = shown(False)
    prompter = TerminalPrompter(terminal.read, terminal.write)
    progress.begin(1, 2, "fetch")
    progress.detail("page 1")
    prompter.tell("A warning.")
    assert out.getvalue().splitlines()[1] == "A warning."


# --- the pipeline ---


def pipeline(tmp_path, steps, progress):
    return Pipeline(steps, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path), progress)


def test_the_pipeline_reports_each_step_with_its_count(tmp_path):
    progress = RecordingProgress()
    steps = [FakeStep("convert", [job("1"), job("2")]), FakeStep("report", [REPORT])]
    pipeline(tmp_path, steps, progress).run()
    assert progress.events == [
        ("begin", "1/2 convert"),
        ("done", "2 jobs"),
        ("begin", "2/2 report"),
        ("done", "report written"),
    ]


def test_one_job_is_not_plural(tmp_path):
    progress = RecordingProgress()
    pipeline(tmp_path, [FakeStep("dedupe", [job("1")]), FakeStep("r", [REPORT])], progress).run()
    assert ("done", "1 job") in progress.events


def test_a_resumed_run_says_which_steps_were_saved(tmp_path):
    first = [
        FakeStep("a", [job("1")]),
        FakeStep("b", error=ValueError("x")),
        FakeStep("c", [REPORT]),
    ]
    pipeline(tmp_path, first, NoProgress()).run()
    progress = RecordingProgress()
    again = [FakeStep("a", [job("1")]), FakeStep("b", [job("1")]), FakeStep("c", [REPORT])]
    pipeline(tmp_path, again, progress).run()
    assert progress.events[:3] == [("skipped", "1/3 a"), ("begin", "2/3 b"), ("done", "1 job")]


def test_a_failing_step_is_reported_as_failed_and_the_run_stops(tmp_path):
    progress = RecordingProgress()
    steps = [
        FakeStep("a", [job("1")]),
        FakeStep("b", error=ValueError("x")),
        FakeStep("c", [REPORT]),
    ]
    pipeline(tmp_path, steps, progress).run()
    assert [kind for kind, _ in progress.events] == ["begin", "done", "begin", "failed"]


def test_the_pipeline_lists_its_step_names(tmp_path):
    steps = [FakeStep("a", [job("1")]), FakeStep("b", [REPORT])]
    assert pipeline(tmp_path, steps, NoProgress()).step_names() == ["a", "b"]


# --- the banner ---


def banner(progress, **kw) -> RunBanner:
    args = dict(
        config="config_local/",
        searches=["remote-us", "seattle", "nyc"],
        sources={"getro": "Fast Forward", "jobspipe": "JobsPipe"},
        progress=progress,
        clock=StepClock(),
        model="haiku",
        ask_above_credits=300,
        ask_above_jobs=300,
    )
    return RunBanner(**(args | kw))


def window(start_day, end_day, month=11, start_month=None):
    return Window(start=date(2026, start_month or month, start_day), end=date(2026, month, end_day))


STEPS = ["fetch", "convert", "dedupe", "new_jobs_filter", "report"]


def two_sources():
    return RunWindows.spanning(
        [
            SourceWindow(source="getro", window=window(10, 12), reason=WindowReason.SINCE_LAST_RUN),
            SourceWindow(
                source="jobspipe",
                window=window(29, 12, start_month=10),
                reason=WindowReason.CATCHING_UP,
            ),
        ]
    )


def test_the_banner_shows_config_searches_model_limits_sources_and_steps():
    assert banner(NoProgress()).lines(two_sources(), STEPS) == [
        "job-radar run, Nov 12 09:14",
        "Config: config_local/ · 3 searches (remote-us, seattle, nyc) · model haiku",
        "Limits: ask above 300 credits, 300 jobs for Claude",
        "Sources: Fast Forward Nov 10 to 12 · JobsPipe Oct 29 to Nov 12 (catching up)",
        "5 steps: fetch, convert, dedupe, new jobs filter, report",
    ]


def test_the_banner_leaves_out_credits_without_a_paid_source_and_names_a_demo_and_a_resume():
    one = RunWindows.spanning(
        [SourceWindow(source="getro", window=window(12, 12), reason=WindowReason.FIRST_RUN)]
    )
    lines = banner(
        NoProgress(),
        ask_above_credits=None,
        searches=["one"],
        demo=True,
        model=None,
        ask_above_jobs=None,
    ).lines(one, STEPS, resuming=True)
    assert lines[0] == "job-radar run (demo) (resuming), Nov 12 09:14"
    assert lines[1] == "Config: config_local/ · 1 search (one) · no LLM, keyword scoring"
    assert lines[2] == "Sources: Fast Forward Nov 12"
    assert not any(line.startswith("Limits") for line in lines)
    lines = banner(NoProgress(), ask_above_credits=None).lines(one, STEPS)
    assert "Limits: ask above 300 jobs for Claude" in lines


def test_the_banner_is_shown_through_the_progress_reporter():
    progress = RecordingProgress()
    banner(progress).show(two_sources(), STEPS)
    assert [kind for kind, _ in progress.events] == ["note"] * 5


# --- live counts ---


def test_describe_counts_the_jobs_it_describes():
    class Describer:
        source = "getro"
        pace = 0.0

        def describe(self, p):
            return "text"

    progress = RecordingProgress()
    jobs_ = [job_of_getro("1"), job_of_getro("2"), job_of_getro("3")]
    DescribeStep({"getro": Describer()}, FakePrompter(), progress).run(jobs_)
    assert progress.details() == [f"description {n} of 3" for n in (1, 2, 3)]


def job_of_getro(source_id):
    one = job(source_id)
    return one.model_copy(update={"postings": (posting(source_id, source="getro"),)})


def test_classify_extract_and_rank_say_which_prompt_they_are_on():
    batch = [described(str(n), "A") for n in range(5)]
    progress = RecordingProgress()
    LlmClassifier(LabellingLlm(), 2, 20, JOB_TYPES, DOMAINS, progress).classify(batch)
    assert progress.details() == ["prompt 1 of 3", "prompt 2 of 3", "prompt 3 of 3"]
    progress = RecordingProgress()
    LlmExtractor(ReadingLlm(), 2, 30, progress).extract(batch)
    assert progress.details() == ["prompt 1 of 3", "prompt 2 of 3", "prompt 3 of 3"]
    progress = RecordingProgress()
    LlmRanker(FakeLlm(), 2, 100, progress).score(jobs(5), RANK_PROFILE)
    assert progress.details() == ["prompt 1 of 3", "prompt 2 of 3", "prompt 3 of 3"]


def test_the_gap_judge_says_it_is_comparing_the_cv():
    progress = RecordingProgress()
    llm = SetLlm(gap_answer(entry("r1", "covered")))
    LlmGapJudge(llm, progress).judge([ask("Python", 0.5)], GAP_PROFILE)
    assert progress.details() == ["comparing the CV, prompt 1"]


def test_getro_says_which_page_and_how_many_jobs_so_far():
    from test_getro import SEARCH, Board, page
    from test_getro import job as getro_job

    pages = [
        page([getro_job(1, date(2026, 11, 5)), getro_job(2, date(2026, 11, 3))], count=4),
        page([getro_job(3, date(2026, 11, 2))], count=4),
    ]
    http = httpx.Client(transport=httpx.MockTransport(Board(pages)))
    progress = RecordingProgress()
    source = GetroSource("997", BoardClient(http, delay=0, sleep=lambda s: None), progress)
    source.fetch(SEARCH, Window(start=date(2026, 1, 1), end=date(2026, 11, 5)))
    assert progress.details() == [
        "Fast Forward page 1, 0 jobs so far",
        "Fast Forward page 2, 2 jobs so far",
    ]


def test_jobspipe_says_which_search_and_day_with_the_jobs_so_far():
    from test_jobspipe import SEARCH, FakeApi

    api = FakeApi(total=30)
    client = BoardClient(httpx.Client(transport=httpx.MockTransport(api)), 0, lambda s: None)
    progress = RecordingProgress()
    source = JobsPipeSource(client, {}, (100, None), FakePrompter(), True, progress)
    from job_radar.models import SearchCriteria

    window_ = Window(start=date(2026, 11, 8), end=date(2026, 11, 9))
    source.fetch_paid(SearchCriteria(searches=(SEARCH,)), window_, cap=100)
    name = SEARCH.name
    assert progress.details() == [
        f"JobsPipe {name}, Nov 9 (day 1 of 2), 0 jobs so far",
        f"JobsPipe {name}, Nov 9 (day 1 of 2), 25 jobs so far",
        f"JobsPipe {name}, Nov 8 (day 2 of 2), 30 jobs so far",
        f"JobsPipe {name}, Nov 8 (day 2 of 2), 55 jobs so far",
    ]


# --- turning it off ---


def run_demo(tmp_path, argv, tty=False, **settings):
    """A demo run through the real command with a terminal on a string; its output."""
    out = io.StringIO()
    terminal = Terminal(out, tty=tty, read=lambda p: "y", width=lambda: 200)
    prompter = TerminalPrompter(terminal.read, terminal.write)
    settings = SettingsFile.defaults(output=str(tmp_path), recommend={"top_n": 3}, **settings)
    factory = AppFactory(
        settings, tmp_path / "config_local", EXAMPLE, FixedClock(10), prompter, {}, terminal
    )
    code = Cli(factory).main(argv)
    return code, out.getvalue()


def test_a_demo_run_shows_a_banner_and_a_line_per_step_by_default(tmp_path):
    code, text = run_demo(tmp_path, ["run", "--demo"])
    assert code == 0
    lines = text.splitlines()
    assert lines[0].startswith("No earlier runs.")  # the window message comes first
    assert any(line.startswith("job-radar run (demo), Nov 5 10:00") for line in lines)
    assert any(line.startswith("Config: config_local_example/ · ") for line in lines)
    assert any(line.startswith("13 steps: fetch, convert, dedupe") for line in lines)
    assert sum(1 for line in lines if line.startswith("[") and "done:" in line) == 13
    assert any(line.startswith("[ 1/13] fetch") for line in lines)


def test_quiet_shows_none_of_it(tmp_path):
    code, text = run_demo(tmp_path, ["run", "--demo", "--quiet"])
    assert code == 0
    assert "job-radar run" not in text and "[ 1/13]" not in text and "steps:" not in text
    assert "\x1b" not in text


def test_the_verbose_setting_turns_it_off_too(tmp_path):
    _, text = run_demo(tmp_path, ["run", "--demo"], verbose=False)
    assert "[ 1/13]" not in text


def test_quiet_output_is_what_it_was_before_progress(tmp_path):
    _, quiet = run_demo(tmp_path, ["run", "--demo", "--quiet"])
    assert quiet == "No earlier runs. Fetching the last 14 days: Oct 22 to Nov 5.\n"


def test_on_a_terminal_a_demo_run_redraws_in_place(tmp_path):
    _, text = run_demo(tmp_path, ["run", "--demo"], tty=True)
    assert CLEAR in text
    assert "[13/13] report" in text and "report written" in text


def test_the_setting_is_on_in_the_defaults_file():
    assert SettingsFile.defaults().verbose is True
