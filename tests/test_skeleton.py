from datetime import date
from pathlib import Path

import httpx
import pytest

from job_radar.checkpoints import Checkpoints, FileCheckpoints, RunStats
from job_radar.cli import Cli
from job_radar.clock import Clock
from job_radar.factory import AppFactory, Settings
from job_radar.llm import ClaudeCli, Llm
from job_radar.model import CandidateProfile, Search, Window
from job_radar.pipeline import Step
from job_radar.ranking import JobRanker, KeywordRanker, LlmRanker
from job_radar.report_writer import FileReportWriter, ReportWriter
from job_radar.result import RunFailed, RunResult, RunSucceeded
from job_radar.sources.base import JobBoardParser, JobBoardSource
from job_radar.sources.demo import DemoParser, DemoSource
from job_radar.sources.getro import GetroParser, GetroSource
from job_radar.steps.convert import ConvertStep
from job_radar.steps.dedupe import DedupeStep, JobKey
from job_radar.steps.fetch import FetchStep
from job_radar.steps.filter import FilterStep
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.steps.report import ReportStep

FOLDER = Path("unused")
SEARCH = Search(name="default", roles=("Software Engineer",))
WINDOW = Window(start=date(2026, 10, 29), end=date(2026, 11, 5))
CHECKPOINTS = FileCheckpoints(FOLDER)
LLM = ClaudeCli("haiku")
RANKER = LlmRanker(LLM, batch_size=20)
PROFILE = CandidateProfile(cv="", preferences="")


def steps():
    """One of each step, in run order."""
    return [
        FetchStep([GetroSource("board", httpx.Client())], SEARCH, WINDOW),
        ConvertStep({"getro": GetroParser()}),
        DedupeStep(JobKey(), date(2026, 11, 5)),
        FilterStep(SEARCH),
        RecommendTopJobsStep(RANKER, PROFILE, top_n=10),
        ReportStep(CHECKPOINTS, FileReportWriter(FOLDER)),
    ]


IMPLEMENTATIONS = [
    (GetroSource("board", httpx.Client()), JobBoardSource),
    (GetroParser(), JobBoardParser),
    (DemoSource(), JobBoardSource),
    (DemoParser(), JobBoardParser),
    (CHECKPOINTS, Checkpoints),
    (CHECKPOINTS, RunStats),
    (RANKER, JobRanker),
    (KeywordRanker(), JobRanker),
    (LLM, Llm),
    (FileReportWriter(FOLDER), ReportWriter),
    (RunSucceeded(location="report.md", summary=""), RunResult),
    (RunFailed(step="fetch", reason=""), RunResult),
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
    cli = Cli(AppFactory(Settings(), Clock()))
    with pytest.raises(SystemExit) as exit_:
        cli.main(["--version"])
    assert exit_.value.code == 0
    assert capsys.readouterr().out.startswith("job-radar ")
