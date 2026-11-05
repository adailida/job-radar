from datetime import date

import pytest
from fakes import FakeStats, MemoryWriter, job, posting

from job_radar.model import (
    CandidateProfile,
    Job,
    RawPage,
    Recommendation,
    Report,
    Search,
    StepCount,
    Window,
)
from job_radar.steps.convert import ConvertStep
from job_radar.steps.dedupe import DedupeStep, JobKey
from job_radar.steps.fetch import FetchStep
from job_radar.steps.filter import FilterStep
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.steps.report import ReportStep

SEARCH = Search(name="default", roles=())
WINDOW = Window(start=date(2026, 10, 29), end=date(2026, 11, 5))
PROFILE = CandidateProfile(cv="", preferences="")


class PagesSource:
    """A board that returns fixed pages."""

    def __init__(self, name: str, pages: int):
        self.name = name
        self._pages = pages

    def fetch(self, search: Search, window: Window) -> list[RawPage]:
        return [RawPage(source=self.name, page=n, body="") for n in range(1, self._pages + 1)]


class OnePostingParser:
    """A parser that turns each page into one posting, named after the page."""

    def __init__(self, source: str):
        self.source = source

    def parse(self, page: RawPage) -> list:
        return [posting(f"{page.page}", source=self.source)]


class ScoreByIdRanker:
    """A ranker whose score for a job is set by its id."""

    def __init__(self, scores: dict[str, int]):
        self._scores = scores

    def score(self, jobs: list[Job], profile: CandidateProfile) -> list[Recommendation]:
        return [Recommendation(job=j, score=self._scores[j.id], reason="r") for j in jobs]


def test_fetch_takes_pages_from_every_board_in_order():
    step = FetchStep([PagesSource("a", 2), PagesSource("b", 1)], SEARCH, WINDOW)
    pages = step.run([])
    assert [(p.source, p.page) for p in pages] == [("a", 1), ("a", 2), ("b", 1)]


def test_convert_sends_each_page_to_its_boards_parser():
    step = ConvertStep({"a": OnePostingParser("a"), "b": OnePostingParser("b")})
    pages = [RawPage(source="b", page=1, body=""), RawPage(source="a", page=2, body="")]
    assert [p.key for p in step.run(pages)] == ["b:1", "a:2"]


def test_convert_fails_on_a_board_without_parser():
    step = ConvertStep({"a": OnePostingParser("a")})
    with pytest.raises(ValueError, match="no parser for source 'x'"):
        step.run([RawPage(source="x", page=1, body="")])


def test_dedupe_merges_postings_with_the_same_key():
    step = DedupeStep(JobKey(), date(2026, 11, 5))
    jobs = step.run([posting("1"), posting("2"), posting("1")])
    assert [(j.id, len(j.postings)) for j in jobs] == [("demo:1", 2), ("demo:2", 1)]
    assert all(j.first_seen == date(2026, 11, 5) for j in jobs)


def test_filter_keeps_every_job_for_now():
    jobs = [job("1"), job("2")]
    assert FilterStep(SEARCH).run(jobs) == jobs


def test_recommend_keeps_top_n_best_first():
    jobs = [job("1"), job("2"), job("3"), job("4")]
    ranker = ScoreByIdRanker({"demo:1": 40, "demo:2": 90, "demo:3": 70, "demo:4": 70})
    top = RecommendTopJobsStep(ranker, PROFILE, top_n=3).run(jobs)
    assert [(r.job.id, r.score) for r in top] == [("demo:2", 90), ("demo:3", 70), ("demo:4", 70)]


def test_report_lists_top_jobs_and_funnel():
    writer = MemoryWriter()
    stats = FakeStats([StepCount(step="fetch", count=2), StepCount(step="convert", count=12)])
    recs = [Recommendation(job=job("1", "Data Engineer"), score=90, reason="Fits well")]
    reports = ReportStep(stats, writer).run(recs)
    assert reports == [Report(location="memory/report.md", summary="1 job recommended")]
    assert "1. **Data Engineer**, Example Org (score 90)" in writer.text
    assert "Fits well" in writer.text
    assert "- fetch: 2\n- convert: 12" in writer.text


def test_report_says_when_nothing_is_recommended():
    writer = MemoryWriter()
    ReportStep(FakeStats([]), writer).run([])
    assert "No jobs to recommend this run." in writer.text
