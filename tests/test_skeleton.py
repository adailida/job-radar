from datetime import date
from pathlib import Path

import httpx
import pytest

from job_radar.asks import AskBuilder, AskSource, MarketAsks, RequirementNames
from job_radar.ats import AtsLinks
from job_radar.checkpoints import Checkpoints, FileCheckpoints, RunStats
from job_radar.cli import Cli
from job_radar.clock import Clock
from job_radar.cost import FileSpendLog
from job_radar.drop_log import DropLog, FileDropLog
from job_radar.error_log import ErrorLog, FileErrorLog
from job_radar.factory import AppFactory
from job_radar.gaps import (
    CvGaps,
    FileGapCache,
    GapBuilder,
    GapCache,
    GapJudge,
    GapSource,
    KeywordGapJudge,
    LlmGapJudge,
)
from job_radar.history import FileRunHistory, RunHistory
from job_radar.html_text import HtmlText
from job_radar.llm import ClaudeCli, Llm
from job_radar.matching import JobMatcher
from job_radar.model import CandidateProfile, RunConfig, Search, SearchCriteria, Window
from job_radar.normalize import Normalizer
from job_radar.openings import OpeningGrouper
from job_radar.pipeline import Step
from job_radar.places import PlaceCodes
from job_radar.prompter import Prompter, TerminalPrompter
from job_radar.ranking import JobRanker, KeywordRanker, LlmRanker
from job_radar.report_renderer import MarkdownRenderer, ReportRenderer
from job_radar.report_writer import FileReportWriter, ReportWriter
from job_radar.result import RunCancelled, RunFailed, RunResult, RunSucceeded
from job_radar.run_lock import FileRunLock, RunLock
from job_radar.seen import FileSeenJobs, SeenJobs
from job_radar.settings import SettingsFile
from job_radar.source_counts import FileSourceCountLog, SourceCountLog
from job_radar.sources.base import JobBoardParser, JobBoardSource, JobDescriber
from job_radar.sources.demo import DemoParser, DemoSource
from job_radar.sources.getro import GetroDescriber, GetroParser, GetroSource
from job_radar.sources.http import BoardClient
from job_radar.steps.convert import ConvertStep
from job_radar.steps.dedupe import DedupeStep, JobKey
from job_radar.steps.describe import DescribeStep
from job_radar.steps.fetch import FetchStep
from job_radar.steps.filter import FilterStep
from job_radar.steps.llm_cap import LlmCapStep
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.steps.report import ReportStep
from job_radar.trends import (
    KeptJobs,
    MarketRuns,
    MarketTrends,
    RunsSource,
    TrendBuilder,
    TrendSource,
)
from job_radar.usage import FilePendingLog, UsageLimitGuard
from job_radar.warning_log import FileWarningLog, TerminalWarnings, WarningLog
from job_radar.words import Words

FOLDER = Path("unused")
WARNINGS = FileWarningLog(FOLDER)
GUARD = UsageLimitGuard(TerminalPrompter(), FilePendingLog(FOLDER), WARNINGS)
SEARCH = SearchCriteria(searches=(Search(name="default", roles=("Software Engineer",)),))
WINDOW = Window(start=date(2026, 10, 29), end=date(2026, 11, 5))
CHECKPOINTS = FileCheckpoints(FOLDER, WINDOW)
LLM = ClaudeCli("haiku")
RANKER = LlmRanker(LLM, batch_size=20)
PROFILE = CandidateProfile(cv="", preferences="")
CLIENT = BoardClient(httpx.Client())


HISTORY = FileRunHistory(FOLDER, WARNINGS)
SEEN = FileSeenJobs(HISTORY, FOLDER, WARNINGS)
RUNS = MarketRuns(HISTORY, SEEN, CHECKPOINTS, WINDOW, RunConfig(searches=(), sources=()))
TRENDS = MarketTrends(RUNS, TrendBuilder("month"))
ASKS = MarketAsks(RUNS, AskBuilder("month", 20, RequirementNames()), WINDOW.end)
GAP_CACHE = FileGapCache(FOLDER / "gaps.jsonl")
GAPS = CvGaps(PROFILE, KeywordGapJudge(), GAP_CACHE, GapBuilder(RequirementNames(), 5), WARNINGS)


def steps():
    """One of each step, in run order."""
    return [
        FetchStep(
            [GetroSource("board", CLIENT)], SEARCH, WINDOW, [], FileSpendLog(FOLDER), WARNINGS, 100
        ),
        ConvertStep({"getro": GetroParser(PlaceCodes())}, FileSourceCountLog(FOLDER), WARNINGS, {}),
        DedupeStep(JobKey(Normalizer(), AtsLinks()), date(2026, 11, 5)),
        FilterStep(SEARCH, WINDOW, JobMatcher(Normalizer()), FileDropLog(FOLDER, Words())),
        DescribeStep({"getro": GetroDescriber("board", CLIENT, HtmlText())}, TerminalPrompter()),
        LlmCapStep(60, TerminalPrompter(), FilePendingLog(FOLDER), WARNINGS),
        RecommendTopJobsStep(RANKER, PROFILE, 10, 40, GUARD, WARNINGS),
        ReportStep(
            CHECKPOINTS,
            MarkdownRenderer(Words()),
            FileReportWriter(FOLDER),
            FileSpendLog(FOLDER),
            FilePendingLog(FOLDER),
            TRENDS,
            ASKS,
            GAPS,
            "run",
            WINDOW,
            None,
            40,
            {"getro": "Fast Forward"},
            FileSourceCountLog(FOLDER),
            CHECKPOINTS,
            OpeningGrouper("job_type", ["engineering"], ["climate"]),
            WARNINGS,
        ),
    ]


IMPLEMENTATIONS = [
    (GetroSource("board", CLIENT), JobBoardSource),
    (GetroParser(PlaceCodes()), JobBoardParser),
    (GetroDescriber("board", CLIENT, HtmlText()), JobDescriber),
    (DemoSource(), JobBoardSource),
    (DemoParser(PlaceCodes()), JobBoardParser),
    (CHECKPOINTS, Checkpoints),
    (CHECKPOINTS, RunStats),
    (CHECKPOINTS, KeptJobs),
    (TRENDS, TrendSource),
    (ASKS, AskSource),
    (GAPS, GapSource),
    (GAP_CACHE, GapCache),
    (LlmGapJudge(LLM), GapJudge),
    (KeywordGapJudge(), GapJudge),
    (RUNS, RunsSource),
    (RANKER, JobRanker),
    (KeywordRanker(), JobRanker),
    (LLM, Llm),
    (FileReportWriter(FOLDER), ReportWriter),
    (MarkdownRenderer(Words()), ReportRenderer),
    (FileDropLog(FOLDER, Words()), DropLog),
    (FileSourceCountLog(FOLDER), SourceCountLog),
    (RunSucceeded(location="report.md", summary=""), RunResult),
    (RunFailed(step="fetch", reason=""), RunResult),
    (RunCancelled(), RunResult),
    (HISTORY, RunHistory),
    (SEEN, SeenJobs),
    (WARNINGS, WarningLog),
    (TerminalWarnings(TerminalPrompter()), WarningLog),
    (FileErrorLog(FOLDER), ErrorLog),
    (FileRunLock(FOLDER), RunLock),
    (TerminalPrompter(), Prompter),
]


@pytest.mark.parametrize(
    ("instance", "interface"),
    IMPLEMENTATIONS,
    ids=lambda x: x.__name__ if isinstance(x, type) else type(x).__name__,
)
def test_class_satisfies_its_interface(instance, interface):
    assert isinstance(instance, interface)


@pytest.mark.parametrize("step", steps(), ids=lambda s: type(s).__name__)
def test_step_satisfies_step_interface(step):
    assert isinstance(step, Step)


def test_step_names_are_unique():
    names = [step.name for step in steps()]
    assert len(names) == len(set(names))


def test_cli_still_shows_version(capsys):
    cli = Cli(AppFactory(SettingsFile.defaults(), Path("local"), Clock(), TerminalPrompter(), {}))
    with pytest.raises(SystemExit) as exit_:
        cli.main(["--version"])
    assert exit_.value.code == 0
    assert capsys.readouterr().out.startswith("job-radar ")
