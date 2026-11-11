from datetime import date

from fakes import job

from job_radar.llm.job_ranker import KeywordRanker
from job_radar.matching.place_codes import PlaceCodes
from job_radar.models import CandidateProfile, Search, SearchCriteria, Window
from job_radar.sources.demo import DemoParser, DemoSource

SEARCH = SearchCriteria(searches=(Search(name="default", roles=()),))
WINDOW = Window(start=date(2026, 10, 29), end=date(2026, 11, 5))


def test_demo_board_serves_every_posting_in_pages():
    pages = DemoSource().fetch(SEARCH, WINDOW)
    assert [p.page for p in pages] == [1, 2]
    postings = [posting for page in pages for posting in DemoParser(PlaceCodes()).parse(page)]
    assert len(postings) == len(DemoSource.POSTINGS)
    assert len({p.key for p in postings}) == len(postings)


def test_demo_postings_are_complete():
    pages = DemoSource().fetch(SEARCH, WINDOW)
    first = DemoParser(PlaceCodes()).parse(pages[0])[0]
    assert first.key == "demo:1"
    assert first.salary is not None and first.salary.min == 140000
    assert first.url.startswith("https://example.org/")


def test_demo_postings_are_dated_back_from_the_window_end():
    pages = DemoSource().fetch(SEARCH, WINDOW)
    first = DemoParser(PlaceCodes()).parse(pages[0])[0]
    assert first.posted_at == date(2026, 11, 2)


def test_keyword_ranker_scores_share_of_title_words_in_profile():
    profile = CandidateProfile(cv="Python data pipelines.", preferences="Remote.")
    jobs = [job("1", "Data Engineer"), job("2", "Python Data Developer"), job("3", "Designer")]
    scores = [(r.score, r.reason) for r in KeywordRanker().score(jobs, profile)]
    assert scores == [
        (50, "Title words in your profile: data"),
        (67, "Title words in your profile: data, python"),
        (0, "No title words in your profile"),
    ]


def test_keyword_ranker_ignores_case_punctuation_and_filler_words():
    profile = CandidateProfile(cv="DATA engineer", preferences="")
    [rec] = KeywordRanker().score([job("1", "Data Engineer, and the APIs")], profile)
    assert rec.score == 67


def test_demo_postings_get_place_codes():
    pages = DemoSource().fetch(SEARCH, WINDOW)
    first = DemoParser(PlaceCodes()).parse(pages[0])[0]
    assert (first.locations[0].country, first.locations[0].region) == ("US", "US-NY")
