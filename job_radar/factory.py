"""Builds the app for one terminal command: the only place that knows concrete classes."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import httpx

from job_radar.app import JobRadarApp
from job_radar.ats import AtsLinks
from job_radar.checkpoints import FileCheckpoints
from job_radar.clock import Clock
from job_radar.drop_log import FileDropLog
from job_radar.history import FileRunHistory, RunFolders
from job_radar.html_text import HtmlText
from job_radar.llm import ClaudeCli
from job_radar.matching import JobMatcher
from job_radar.model import CandidateProfile, SearchCriteria, Window
from job_radar.normalize import Normalizer
from job_radar.pipeline import Pipeline, Step
from job_radar.places import PlaceCodes
from job_radar.profile import DEMO_PROFILE, ProfileLoader
from job_radar.prompter import Prompter
from job_radar.ranking import JobRanker, KeywordRanker, LlmRanker
from job_radar.report_renderer import MarkdownRenderer
from job_radar.report_writer import FileReportWriter
from job_radar.resume import ResumeOffer
from job_radar.runs_command import RunsCommand
from job_radar.searches import DEMO_SEARCHES, SearchesFile
from job_radar.seen import FileSeenJobs
from job_radar.settings import Settings
from job_radar.sources.base import JobBoardParser, JobBoardSource, JobDescriber
from job_radar.sources.demo import DemoParser, DemoSource
from job_radar.sources.getro import GetroDescriber, GetroParser, GetroSource
from job_radar.sources.http import BoardClient
from job_radar.steps.convert import ConvertStep
from job_radar.steps.dedupe import DedupeStep, JobKey
from job_radar.steps.describe import DescribeStep
from job_radar.steps.fetch import FetchStep
from job_radar.steps.filter import FilterStep
from job_radar.steps.new_jobs_filter import NewJobsFilterStep
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.steps.report import ReportStep
from job_radar.window import WindowPlanner
from job_radar.window_chooser import WindowChooser
from job_radar.words import Words


@dataclass(frozen=True)
class Parts:
    """What differs between a real run and a demo run: boards, searches, ranker and profile."""

    sources: list[JobBoardSource]
    parsers: list[JobBoardParser]
    describers: list[JobDescriber]  # only for boards whose postings come without descriptions
    criteria: SearchCriteria
    ranker: JobRanker
    profile: CandidateProfile


class AppFactory:
    """Builds the app and everything it uses for one command (Factory).

    Wires concrete classes together, so every other class depends only on
    interfaces. Stateless: holds only the settings, the user's folder, the
    clock and the prompter.
    """

    USER_AGENT = "job-radar (+https://github.com/adailida/job-radar)"

    def __init__(self, settings: Settings, local: Path, clock: Clock, prompter: Prompter) -> None:
        """Keep the settings, the user's folder, the clock and the prompter to build from."""
        self._settings = settings
        self._local = local
        self._clock = clock
        self._prompter = prompter

    def create(self, demo: bool = False) -> JobRadarApp:
        """Build the app, reading the user's files first so a setup error stops before anything.

        With `demo`, the run uses the built-in demo board, a made-up profile and
        keyword scoring: no network, no LLM, nothing from the user's folder.
        Demo runs keep their own history, so they never move a real run's window.
        """
        parts = self._demo() if demo else self._real()
        runs = self._runs(demo)
        planner = WindowPlanner(self._settings.lookback_days)
        history = FileRunHistory(runs)
        chooser = WindowChooser(history, planner, self._prompter, self._clock)
        offer = ResumeOffer(history, self._prompter, Words())
        return JobRadarApp(offer, chooser, partial(self._pipeline, parts, runs))

    def runs_command(self, demo: bool = False) -> RunsCommand:
        """Build the `runs` and `delete` commands, for real runs or demo runs."""
        runs = self._runs(demo)
        return RunsCommand(FileRunHistory(runs), RunFolders(runs), self._prompter, Words())

    def _runs(self, demo: bool) -> Path:
        """The folder that holds one folder per run: demo runs keep their own."""
        return self._settings.output / ("demo" if demo else "runs")

    def _pipeline(
        self,
        parts: Parts,
        runs: Path,
        window: Window,
        not_covered: Window | None,
        run_id: str | None,
    ) -> Pipeline:
        """Build the steps in order for the run's window, in a new folder or the resumed one."""
        folder = runs / (run_id or self._clock.stamp())
        folder.mkdir(parents=True, exist_ok=run_id is not None)
        checkpoints = FileCheckpoints(
            folder, window, not_covered, keep={FilterStep.name: FileSeenJobs.FILE}
        )
        normalizer = Normalizer()
        words = Words()
        steps: list[Step] = [
            FetchStep(parts.sources, parts.criteria, window),
            ConvertStep({parser.source: parser for parser in parts.parsers}),
            DedupeStep(JobKey(normalizer, AtsLinks()), window.end),
            NewJobsFilterStep(
                FileSeenJobs(FileRunHistory(runs), runs), window.end, self._settings.new_only
            ),
            FilterStep(parts.criteria, window, JobMatcher(normalizer), FileDropLog(folder, words)),
            DescribeStep({d.source: d for d in parts.describers}, self._prompter),
            RecommendTopJobsStep(
                parts.ranker,
                parts.profile,
                self._settings.recommend.top_n,
                self._settings.recommend.min_score,
            ),
            ReportStep(
                checkpoints,
                MarkdownRenderer(words),
                FileReportWriter(folder),
                folder.name,
                window,
                not_covered,
                self._settings.recommend.min_score,
            ),
        ]
        return Pipeline(steps, checkpoints)

    def _demo(self) -> Parts:
        """The boards, searches, ranker and profile of a demo run."""
        return Parts(
            [DemoSource()],
            [DemoParser(PlaceCodes())],
            [],
            DEMO_SEARCHES,
            KeywordRanker(),
            DEMO_PROFILE,
        )

    def _real(self) -> Parts:
        """The boards, ranker and profile of a real run: Fast Forward, Claude and the user's files.

        Reads the searches, the CV and the preferences and checks `claude` is
        logged in first, so a missing file or login stops the run before
        anything is fetched.
        """
        criteria = SearchesFile(self._local / "profile.yaml").load()
        profile = ProfileLoader(self._local).load()
        llm_settings = self._settings.llm
        llm = ClaudeCli(llm_settings.model, llm_settings.timeout_seconds)
        llm.check()
        ranker = LlmRanker(llm, llm_settings.batch_size, llm_settings.max_description_chars)
        http = httpx.Client(headers={"User-Agent": self.USER_AGENT}, timeout=20)
        getro = BoardClient(http)
        network = self._settings.sources.getro.network
        return Parts(
            [GetroSource(network, getro)],
            [GetroParser(PlaceCodes())],
            [GetroDescriber(network, getro, HtmlText())],
            criteria,
            ranker,
            profile,
        )
