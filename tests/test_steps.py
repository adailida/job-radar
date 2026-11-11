from datetime import date

import pytest
from fakes import MemorySourceCountLog, MemorySpendLog, MemoryWarningLog, guard, job, posting

from job_radar.models import (
    CandidateProfile,
    Job,
    RawPage,
    Recommendation,
    Search,
    SearchCriteria,
    SourceCount,
    Window,
)
from job_radar.pipeline.steps.convert import ConvertStep
from job_radar.pipeline.steps.fetch import FetchStep
from job_radar.pipeline.steps.recommend import RecommendTopJobsStep

SEARCH = SearchCriteria(searches=(Search(name="default", roles=()),))
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
    step = FetchStep(
        [PagesSource("a", 2), PagesSource("b", 1)],
        SEARCH,
        WINDOW,
        [],
        MemorySpendLog(),
        MemoryWarningLog(),
        100,
    )
    pages = step.run([])
    assert [(p.source, p.page) for p in pages] == [("a", 1), ("a", 2), ("b", 1)]


def test_convert_sends_each_page_to_its_boards_parser():
    step = ConvertStep(
        {"a": OnePostingParser("a"), "b": OnePostingParser("b")},
        MemorySourceCountLog(),
        MemoryWarningLog(),
        {},
    )
    pages = [RawPage(source="b", page=1, body=""), RawPage(source="a", page=2, body="")]
    assert [p.key for p in step.run(pages)] == ["b:1", "a:2"]


def test_convert_counts_the_postings_each_board_gave_a_board_with_none_too():
    counts = MemorySourceCountLog()
    step = ConvertStep(
        {"a": OnePostingParser("a"), "b": OnePostingParser("b")}, counts, MemoryWarningLog(), {}
    )
    step.run([RawPage(source="a", page=1, body=""), RawPage(source="a", page=2, body="")])
    assert counts.counts() == [
        SourceCount(source="a", postings=2),
        SourceCount(source="b", postings=0),
    ]


def test_convert_fails_on_a_board_without_parser():
    step = ConvertStep({"a": OnePostingParser("a")}, MemorySourceCountLog(), MemoryWarningLog(), {})
    with pytest.raises(ValueError, match="no parser for source 'x'"):
        step.run([RawPage(source="x", page=1, body="")])


def test_recommend_keeps_top_n_best_first():
    jobs = [job("1"), job("2"), job("3"), job("4")]
    ranker = ScoreByIdRanker({"demo:1": 40, "demo:2": 90, "demo:3": 70, "demo:4": 70})
    top = RecommendTopJobsStep(
        ranker, PROFILE, top_n=3, min_score=0, guard=guard(), warnings=MemoryWarningLog()
    ).run(jobs)
    assert [(r.job.id, r.score) for r in top] == [("demo:2", 90), ("demo:3", 70), ("demo:4", 70)]


def test_recommend_leaves_out_jobs_below_the_minimum_score():
    jobs = [job("1"), job("2"), job("3")]
    ranker = ScoreByIdRanker({"demo:1": 39, "demo:2": 40, "demo:3": 85})
    top = RecommendTopJobsStep(
        ranker, PROFILE, top_n=10, min_score=40, guard=guard(), warnings=MemoryWarningLog()
    ).run(jobs)
    assert [(r.job.id, r.score) for r in top] == [("demo:3", 85), ("demo:2", 40)]


def test_recommend_gives_nothing_when_no_job_reaches_the_minimum():
    ranker = ScoreByIdRanker({"demo:1": 18})
    assert (
        RecommendTopJobsStep(
            ranker, PROFILE, top_n=10, min_score=40, guard=guard(), warnings=MemoryWarningLog()
        ).run([job("1")])
        == []
    )
