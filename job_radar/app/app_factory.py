"""Builds the app for one terminal command: the only place that knows concrete classes."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import httpx

from job_radar.app.cost_check import CostCheck
from job_radar.app.job_radar_app import JobRadarApp
from job_radar.app.resume_offer import ResumeOffer
from job_radar.app.runs_command import RunsCommand
from job_radar.app.window import WindowChooser, WindowPlanner
from job_radar.config.profile_loader import ProfileLoader
from job_radar.config.searches_file import SearchesFile
from job_radar.config.secrets import Secrets
from job_radar.config.settings import Settings
from job_radar.config.yaml_file import ConfigError
from job_radar.llm.classifier import Classifier, LlmClassifier, TitleClassifier
from job_radar.llm.extractor import Extractor, KeywordExtractor, LlmExtractor
from job_radar.llm.gap_judge import GapJudge, KeywordGapJudge, LlmGapJudge
from job_radar.llm.job_ranker import JobRanker, KeywordRanker, LlmRanker
from job_radar.llm.llm import ClaudeCli
from job_radar.llm.usage_limit_guard import UsageLimitGuard
from job_radar.matching.ats_links import AtsLinks
from job_radar.matching.job_key import JobKey
from job_radar.matching.job_matcher import JobMatcher
from job_radar.matching.normalizer import Normalizer
from job_radar.matching.place_codes import PlaceCodes
from job_radar.models import Approval, CandidateProfile, RunConfig, SearchCriteria, Window
from job_radar.pipeline.pipeline import Pipeline, Step
from job_radar.pipeline.steps.carried_over import CarriedOverStep
from job_radar.pipeline.steps.classify import ClassifyStep
from job_radar.pipeline.steps.convert import ConvertStep
from job_radar.pipeline.steps.dedupe import DedupeStep
from job_radar.pipeline.steps.describe import DescribeStep
from job_radar.pipeline.steps.extract import ExtractStep
from job_radar.pipeline.steps.fetch import FetchStep
from job_radar.pipeline.steps.filter import FilterStep
from job_radar.pipeline.steps.llm_cap import LlmCapStep
from job_radar.pipeline.steps.match import MatchStep
from job_radar.pipeline.steps.new_jobs_filter import NewJobsFilterStep
from job_radar.pipeline.steps.recommend import RecommendTopJobsStep
from job_radar.pipeline.steps.report import ReportStep
from job_radar.report.asks import AskBuilder, MarketAsks, RequirementNames
from job_radar.report.gaps import CvGaps, GapBuilder
from job_radar.report.opening_grouper import OpeningGrouper
from job_radar.report.report_renderer import MarkdownRenderer
from job_radar.report.report_writer import FileReportWriter
from job_radar.report.trends import MarketRuns, MarketTrends, TrendBuilder
from job_radar.report.words import Words
from job_radar.sources.base import JobBoardParser, JobBoardSource, JobDescriber, PaidSource
from job_radar.sources.board_client import BoardClient
from job_radar.sources.demo import DemoParser, DemoSource
from job_radar.sources.getro import GetroDescriber, GetroParser, GetroSource
from job_radar.sources.jobspipe import JobsPipeParser, JobsPipeSource
from job_radar.storage.checkpoints import FileCheckpoints
from job_radar.storage.drop_log import FileDropLog
from job_radar.storage.error_log import ErrorLog, FileErrorLog
from job_radar.storage.gap_cache import FileGapCache
from job_radar.storage.pending_log import FilePendingLog, LastRunPending
from job_radar.storage.run_history import FileRunHistory, RunFolders
from job_radar.storage.run_lock import FileRunLock
from job_radar.storage.seen_jobs import FileSeenJobs
from job_radar.storage.source_count_log import FileSourceCountLog
from job_radar.storage.spend_log import FileSpendLog
from job_radar.storage.warning_log import FileWarningLog, TerminalWarnings
from job_radar.utils.clock import Clock
from job_radar.utils.html_text import HtmlText
from job_radar.utils.prompter import Prompter


@dataclass(frozen=True)
class Parts:
    """What differs between a real run and a demo run: boards, searches, LLM parts and profile."""

    sources: list[JobBoardSource]
    parsers: list[JobBoardParser]
    describers: list[JobDescriber]  # only for boards whose postings come without descriptions
    criteria: SearchCriteria
    classifier: Classifier
    extractor: Extractor
    ranker: JobRanker
    judge: GapJudge
    profile: CandidateProfile


class AppFactory:
    """Builds the app and everything it uses for one command (Factory).

    Wires concrete classes together, so every other class depends only on
    interfaces. Stateless: holds only the settings, the user's folder, the
    example folder the demo runs on, the clock, the prompter and where
    secrets are read.
    """

    USER_AGENT = "job-radar (+https://github.com/adailida/job-radar)"

    def __init__(
        self,
        settings: Settings,
        local: Path,
        example: Path,
        clock: Clock,
        prompter: Prompter,
        secrets: Secrets,
    ) -> None:
        """Keep the settings, the user's and the example folders, the clock and the prompter."""
        self._settings = settings
        self._local = local
        self._example = example
        self._secrets = secrets
        self._clock = clock
        self._prompter = prompter

    def create(self, demo: bool = False) -> JobRadarApp:
        """Build the app, reading the user's files first so a setup error stops before anything.

        With `demo`, the run uses the built-in demo board, the made-up person
        in the example folder and keyword scoring: no network, no LLM, nothing
        from the user's folder. Demo runs keep their own history, so they never
        move a real run's window.
        """
        parts = self._demo() if demo else self._real()
        runs = self._runs(demo)
        planner = WindowPlanner(self._settings.lookback_days)
        history = FileRunHistory(runs, TerminalWarnings(self._prompter))
        chooser = WindowChooser(history, planner, self._prompter, self._clock)
        offer = ResumeOffer(history, self._prompter, Words())
        paid = [source for source in parts.sources if isinstance(source, PaidSource)]
        cost = CostCheck(paid, parts.criteria, self._prompter)
        pipeline = partial(self._pipeline, parts, runs, self._gap_cache(demo))
        lock = FileRunLock(self._settings.output)
        return JobRadarApp(offer, chooser, cost, pipeline, lock)

    def runs_command(self, demo: bool = False) -> RunsCommand:
        """Build the `runs` and `delete` commands, for real runs or demo runs."""
        runs = self._runs(demo)
        history = FileRunHistory(runs, TerminalWarnings(self._prompter))
        return RunsCommand(history, RunFolders(runs), self._prompter, Words())

    def error_log(self) -> ErrorLog:
        """Where an unexpected error outside any run folder is written: the output folder."""
        return FileErrorLog(self._settings.output)

    def _runs(self, demo: bool) -> Path:
        """The folder that holds one folder per run: demo runs keep their own."""
        return self._settings.output / ("demo" if demo else "runs")

    def _gap_cache(self, demo: bool) -> Path:
        """The file keeping the CV comparison, outside the run folders; demo runs keep their own."""
        return self._settings.output / "cache" / ("demo-gaps.jsonl" if demo else "gaps.jsonl")

    def _pipeline(
        self,
        parts: Parts,
        runs: Path,
        gap_cache: Path,
        window: Window,
        not_covered: Window | None,
        run_id: str | None,
        approvals: list[Approval],
    ) -> Pipeline:
        """Build the steps in order for the run's window, in a new folder or the resumed one."""
        folder = runs / (run_id or self._clock.stamp())
        folder.mkdir(parents=True, exist_ok=run_id is not None)
        config = RunConfig(
            searches=parts.criteria.searches, sources=tuple(s.name for s in parts.sources)
        )
        checkpoints = FileCheckpoints(
            folder, window, not_covered, keep={ExtractStep.name: FileSeenJobs.FILE}, config=config
        )
        normalizer = Normalizer()
        words = Words()
        warnings = FileWarningLog(folder)
        history = FileRunHistory(runs, warnings)
        seen = FileSeenJobs(history, runs, warnings)
        spend = FileSpendLog(folder)
        counts = FileSourceCountLog(folder)
        pending = FilePendingLog(folder)
        guard = UsageLimitGuard(self._prompter, pending, warnings)
        market = MarketRuns(history, seen, checkpoints, window, config)
        labels = {source.name: source.label for source in parts.sources}
        period = self._settings.trend_period
        per_type = self._settings.report.requirements_per_type
        names = RequirementNames()
        gaps = CvGaps(
            parts.profile,
            parts.judge,
            FileGapCache(gap_cache),
            GapBuilder(names, self._settings.report.gap_suggestions),
            warnings,
        )
        steps: list[Step] = [
            FetchStep(
                parts.sources,
                parts.criteria,
                window,
                approvals,
                spend,
                warnings,
                self._settings.alerts.low_credits,
            ),
            ConvertStep(
                {parser.source: parser for parser in parts.parsers}, counts, warnings, labels
            ),
            DedupeStep(JobKey(normalizer, AtsLinks()), window.end),
            NewJobsFilterStep(seen, window.end, self._settings.new_only),
            FilterStep(parts.criteria, window, JobMatcher(normalizer), FileDropLog(folder, words)),
            CarriedOverStep(LastRunPending(history, runs)),
            DescribeStep({d.source: d for d in parts.describers}, self._prompter),
            LlmCapStep(self._settings.llm.max_jobs_per_run, self._prompter, pending, warnings),
            ClassifyStep(parts.classifier, self._prompter, guard, warnings),
            MatchStep(parts.criteria, JobMatcher(normalizer)),
            ExtractStep(parts.extractor, self._prompter, guard, warnings),
            RecommendTopJobsStep(
                parts.ranker,
                parts.profile,
                self._settings.recommend.top_n,
                self._settings.recommend.min_score,
                guard,
                warnings,
            ),
            ReportStep(
                checkpoints,
                MarkdownRenderer(words),
                FileReportWriter(folder),
                spend,
                pending,
                MarketTrends(market, TrendBuilder(period)),
                MarketAsks(market, AskBuilder(period, per_type, names), window.end),
                gaps,
                folder.name,
                window,
                not_covered,
                self._settings.recommend.min_score,
                labels,
                counts,
                checkpoints,
                OpeningGrouper(
                    self._settings.report.group_by,
                    list(self._settings.job_types),
                    list(self._settings.domains),
                ),
                warnings,
            ),
        ]
        return Pipeline(steps, checkpoints, FileErrorLog(folder))

    def _searches(self, folder: Path) -> SearchCriteria:
        """The searches in a folder's `profile.yaml`, with every domain they name checked."""
        criteria = SearchesFile(folder / "profile.yaml").load()
        self._check_domains(criteria)
        return criteria

    def _check_domains(self, criteria: SearchCriteria) -> None:
        """Every domain a search names is one the settings define."""
        known = self._settings.domains
        for search in criteria.searches:
            unknown = [
                d for d in (search.domains.values if search.domains else ()) if d not in known
            ]
            if unknown:
                raise ConfigError(
                    f"profile.yaml: searches.{search.name}.domains: unknown {', '.join(unknown)}; "
                    f"the settings define {', '.join(known)}"
                )

    def _jobspipe(self) -> JobsPipeSource:
        """The JobsPipe source, with its key from the environment or `config_local/.env`."""
        jobspipe = self._settings.sources.jobspipe
        key = self._secrets.get(jobspipe.api_key_env)
        if not key:
            raise ConfigError(
                f"{jobspipe.api_key_env} is not set: add it to config_local/.env, "
                "or set sources.jobspipe.enabled: false in config_local/settings.yaml"
            )
        http = httpx.Client(
            headers={"User-Agent": self.USER_AGENT, "Authorization": f"Bearer {key}"}, timeout=60
        )
        client = BoardClient(http, jobspipe.delay_seconds)
        per_run, budget = JobsPipeSource.PLANS[jobspipe.plan]
        limits = (jobspipe.max_jobs_per_run or per_run, jobspipe.monthly_budget or budget)
        return JobsPipeSource(
            client, jobspipe.filters, limits, self._prompter, jobspipe.match_if_missing
        )

    def _demo(self) -> Parts:
        """The parts of a demo run: the demo board, keyword scoring and the example person.

        The searches, CV and preferences come from the example folder, so the
        demo shows what a copy of it in `config_local/` would do. No LLM, no
        network, nothing from the user's folder.
        """
        return Parts(
            [DemoSource()],
            [DemoParser(PlaceCodes())],
            [],
            self._searches(self._example),
            TitleClassifier(),
            KeywordExtractor(),
            KeywordRanker(),
            KeywordGapJudge(),
            ProfileLoader(self._example).load(),
        )

    def _real(self) -> Parts:
        """The boards, ranker and profile of a real run: the boards, Claude and the user's files.

        Reads the searches, the CV, the preferences and any API key, then
        checks `claude` is logged in, so a missing file, key or login stops the
        run before anything is fetched. JobsPipe joins Fast Forward when it is on.
        """
        criteria = self._searches(self._local)
        profile = ProfileLoader(self._local).load()
        http = httpx.Client(headers={"User-Agent": self.USER_AGENT}, timeout=20)
        getro = BoardClient(http)
        network = self._settings.sources.getro.network
        sources: list[JobBoardSource] = [GetroSource(network, getro)]
        parsers: list[JobBoardParser] = [GetroParser(PlaceCodes())]
        if self._settings.sources.jobspipe.enabled:
            sources.append(self._jobspipe())
            parsers.append(JobsPipeParser(PlaceCodes(), HtmlText()))
        llm_settings = self._settings.llm
        llm = ClaudeCli(llm_settings.model, llm_settings.timeout_seconds)
        llm.check()
        ranker = LlmRanker(llm, llm_settings.batch_size, llm_settings.max_description_chars)
        classifier = LlmClassifier(
            llm,
            llm_settings.classify_batch_size,
            llm_settings.classify_description_chars,
            self._settings.job_types,
            self._settings.domains,
        )
        extractor = LlmExtractor(
            llm, llm_settings.extract_batch_size, llm_settings.extract_description_chars
        )
        return Parts(
            sources,
            parsers,
            [GetroDescriber(network, getro, HtmlText())],
            criteria,
            classifier,
            extractor,
            ranker,
            LlmGapJudge(llm),
            profile,
        )
