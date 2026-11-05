"""Builds the app for one terminal command: the only place that knows concrete classes."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import httpx

from job_radar.app import JobRadarApp
from job_radar.checkpoints import FileCheckpoints
from job_radar.clock import Clock
from job_radar.history import FileRunHistory
from job_radar.llm import ClaudeCli
from job_radar.model import CandidateProfile, Model, Search, Window
from job_radar.pipeline import Pipeline, Step
from job_radar.profile import DEMO_PROFILE, ProfileLoader
from job_radar.prompter import Prompter
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
from job_radar.window import WindowPlanner
from job_radar.window_chooser import WindowChooser


class Settings(Model):
    """Everything a run can be configured with."""

    # TODO(task 10): load from a settings file.
    output: Path = Path("output")  # run folders go under output/runs/, demo runs under output/demo/
    local: Path = Path("local")  # the user's CV and preferences
    board: str = ""  # TODO(task 5): Fast Forward's board name on Getro.
    search: Search = Search(name="default", roles=())
    lookback_days: int = 14  # how far back a run may reach: a first run, or after a long break
    model: str = "haiku"
    batch_size: int = 20
    top_n: int = 10


@dataclass(frozen=True)
class Parts:
    """What differs between a real run and a demo run: the boards, the ranker and the profile."""

    sources: list[JobBoardSource]
    parsers: list[JobBoardParser]
    ranker: JobRanker
    profile: CandidateProfile


class AppFactory:
    """Builds the app and everything it uses for one command (Factory).

    Wires concrete classes together, so every other class depends only on
    interfaces. Stateless: holds only the settings, the clock and the prompter.
    """

    def __init__(self, settings: Settings, clock: Clock, prompter: Prompter) -> None:
        """Keep the settings, the clock and the prompter the app is built from."""
        self._settings = settings
        self._clock = clock
        self._prompter = prompter

    def create(self, demo: bool = False) -> JobRadarApp:
        """Build the app, reading the user's files first so a setup error stops before anything.

        With `demo`, the run uses the built-in demo board, a made-up profile and
        keyword scoring: no network, no LLM, nothing from the user's folder.
        Demo runs keep their own history, so they never move a real run's window.
        """
        parts = self._demo() if demo else self._real()
        runs = self._settings.output / ("demo" if demo else "runs")
        planner = WindowPlanner(self._settings.lookback_days)
        chooser = WindowChooser(FileRunHistory(runs), planner, self._prompter, self._clock)
        return JobRadarApp(chooser, partial(self._pipeline, parts, runs))

    def _pipeline(self, parts: Parts, runs: Path, window: Window) -> Pipeline:
        """Make the run's folder and build the steps in order, for the agreed window."""
        folder = runs / self._clock.stamp()
        folder.mkdir(parents=True)
        checkpoints = FileCheckpoints(folder, window)
        search = self._settings.search
        steps: list[Step] = [
            FetchStep(parts.sources, search, window),
            ConvertStep({parser.source: parser for parser in parts.parsers}),
            DedupeStep(JobKey(), window.end),
            FilterStep(search, window),
            RecommendTopJobsStep(parts.ranker, parts.profile, self._settings.top_n),
            ReportStep(checkpoints, FileReportWriter(folder), window),
        ]
        return Pipeline(steps, checkpoints)

    def _demo(self) -> Parts:
        """The boards, ranker and profile of a demo run."""
        return Parts([DemoSource()], [DemoParser()], KeywordRanker(), DEMO_PROFILE)

    def _real(self) -> Parts:
        """The boards, ranker and profile of a real run, from the settings and the user's folder."""
        settings = self._settings
        return Parts(
            [GetroSource(settings.board, httpx.Client())],
            [GetroParser()],
            LlmRanker(ClaudeCli(settings.model), settings.batch_size),
            ProfileLoader(settings.local).load(),
        )
