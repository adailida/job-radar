from datetime import date
from pathlib import Path

import httpx
import pytest

from job_radar.ats import AtsLinks
from job_radar.checkpoints import Checkpoints, FileCheckpoints, RunStats
from job_radar.cli import Cli
from job_radar.clock import Clock
from job_radar.cost import FileSpendLog
from job_radar.drop_log import DropLog, FileDropLog
from job_radar.factory import AppFactory
from job_radar.history import FileRunHistory, RunHistory
from job_radar.html_text import HtmlText
from job_radar.llm import ClaudeCli, Llm
from job_radar.matching import JobMatcher
from job_radar.model import CandidateProfile, Search, SearchCriteria, Window
from job_radar.normalize import Normalizer
from job_radar.pipeline import Step
from job_radar.places import PlaceCodes
from job_radar.prompter import Prompter, TerminalPrompter
from job_radar.ranking import JobRanker, KeywordRanker, LlmRanker
from job_radar.report_renderer import MarkdownRenderer, ReportRenderer
from job_radar.report_writer import FileReportWriter, ReportWriter
from job_radar.result import RunCancelled, RunFailed, RunResult, RunSucceeded
from job_radar.settings import SettingsFile
from job_radar.sources.base import JobBoardParser, JobBoardSource, JobDescriber
from job_radar.sources.demo import DemoParser, DemoSource
from job_radar.sources.getro import GetroDescriber, GetroParser, GetroSource
from job_radar.sources.http import BoardClient
from job_radar.steps.convert import ConvertStep
from job_radar.steps.dedupe import DedupeStep, JobKey
from job_radar.steps.describe import DescribeStep
from job_radar.steps.fetch import FetchStep
from job_radar.steps.filter import FilterStep
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.steps.report import ReportStep
from job_radar.usage import FilePendingLog, UsageLimitGuard
from job_radar.words import Words

FOLDER = Path("unused")
GUARD = UsageLimitGuard(TerminalPrompter(), FilePendingLog(FOLDER))
SEARCH = SearchCriteria(searches=(Search(name="default", roles=("Software Engineer",)),))
WINDOW = Window(start=date(2026, 10, 29), end=date(2026, 11, 5))
CHECKPOINTS = FileCheckpoints(FOLDER, WINDOW)
LLM = ClaudeCli("haiku")
RANKER = LlmRanker(LLM, batch_size=20)
PROFILE = CandidateProfile(cv="", preferences="")
CLIENT = BoardClient(httpx.Client())


def steps():
    """One of each step, in run order."""
    return [
        FetchStep([GetroSource("board", CLIENT)], SEARCH, WINDOW, [], FileSpendLog(FOLDER)),
        ConvertStep({"getro": GetroParser(PlaceCodes())}),
        DedupeStep(JobKey(Normalizer(), AtsLinks()), date(2026, 11, 5)),
        FilterStep(SEARCH, WINDOW, JobMatcher(Normalizer()), FileDropLog(FOLDER, Words())),
        DescribeStep({"getro": GetroDescriber("board", CLIENT, HtmlText())}, TerminalPrompter()),
        RecommendTopJobsStep(RANKER, PROFILE, top_n=10, min_score=40, guard=GUARD),
        ReportStep(
            CHECKPOINTS,
            MarkdownRenderer(Words()),
            FileReportWriter(FOLDER),
            FileSpendLog(FOLDER),
            FilePendingLog(FOLDER),
            "run",
            WINDOW,
            None,
            40,
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
    (RANKER, JobRanker),
    (KeywordRanker(), JobRanker),
    (LLM, Llm),
    (FileReportWriter(FOLDER), ReportWriter),
    (MarkdownRenderer(Words()), ReportRenderer),
    (FileDropLog(FOLDER, Words()), DropLog),
    (RunSucceeded(location="report.md", summary=""), RunResult),
    (RunFailed(step="fetch", reason=""), RunResult),
    (RunCancelled(), RunResult),
    (FileRunHistory(FOLDER), RunHistory),
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
