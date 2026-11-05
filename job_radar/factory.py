"""Builds the app for one terminal command: the only place that knows concrete classes."""

from datetime import timedelta
from pathlib import Path

import httpx

from job_radar.app import JobRadarApp
from job_radar.checkpoints import FileCheckpoints
from job_radar.clock import Clock
from job_radar.llm import ClaudeCli
from job_radar.model import CandidateProfile, Model, Search, Window
from job_radar.pipeline import Pipeline, Step
from job_radar.profile import DEMO_PROFILE, ProfileLoader
from job_radar.ranking import JobRanker, KeywordRanker, LlmRanker
from job_radar.report_writer import FileReportWriter
from job_radar.sources.base import JobBoardParser, JobBoardSource
from job_radar.sources.demo import DemoParser, DemoSource
from job_radar.sources.getro import GetroParser, GetroSource
from job_radar.steps.convert import ConvertStep
from job_radar.steps.dedupe import DedupeStep, JobKey
from job_radar.steps.fetch import FetchStep
from job_radar.steps.filter import FilterStep
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.steps.report import ReportStep


class Settings(Model):
    """Everything a run can be configured with."""

    # TODO(task 10): load from a settings file.
    output: Path = Path("output")  # run folders go under output/runs/
    local: Path = Path("local")  # the user's CV and preferences
    board: str = ""  # TODO(task 5): Fast Forward's board name on Getro.
    search: Search = Search(name="default", roles=())
    window_days: int = 7
    model: str = "haiku"
    batch_size: int = 20
    top_n: int = 10


class AppFactory:
    """Builds the app and everything it uses for one command (Factory).

    Wires concrete classes together, so every other class depends only on
    interfaces. Stateless: holds only the settings and the clock.
    """

    def __init__(self, settings: Settings, clock: Clock) -> None:
        """Keep the settings and the clock the app is built from."""
        self._settings = settings
        self._clock = clock

    def create(self, demo: bool = False) -> JobRadarApp:
        """Build the app: a new run folder, the steps in order, and the pipeline.

        With `demo`, the run uses the built-in demo board, a made-up profile and
        keyword scoring: no network, no LLM, nothing from the user's folder.
        """
        # The user's files are read before the run folder exists, so a setup error leaves nothing.
        sources, parsers, ranker, profile = self._demo() if demo else self._real()
        folder = self._settings.output / "runs" / self._clock.stamp()
        folder.mkdir(parents=True)
        checkpoints = FileCheckpoints(folder)
        today = self._clock.now().date()
        window = Window(start=today - timedelta(days=self._settings.window_days), end=today)
        search = self._settings.search
        steps: list[Step] = [
            FetchStep(sources, search, window),
            ConvertStep({parser.source: parser for parser in parsers}),
            DedupeStep(JobKey(), today),
            FilterStep(search),
            RecommendTopJobsStep(ranker, profile, self._settings.top_n),
            ReportStep(checkpoints, FileReportWriter(folder)),
        ]
        return JobRadarApp(Pipeline(steps, checkpoints))

    def _demo(
        self,
    ) -> tuple[list[JobBoardSource], list[JobBoardParser], JobRanker, CandidateProfile]:
        """The boards, ranker and profile of a demo run."""
        return [DemoSource()], [DemoParser()], KeywordRanker(), DEMO_PROFILE

    def _real(
        self,
    ) -> tuple[list[JobBoardSource], list[JobBoardParser], JobRanker, CandidateProfile]:
        """The boards, ranker and profile of a real run, from the settings and the user's folder."""
        settings = self._settings
        return (
            [GetroSource(settings.board, httpx.Client())],
            [GetroParser()],
            LlmRanker(ClaudeCli(settings.model), settings.batch_size),
            ProfileLoader(settings.local).load(),
        )
