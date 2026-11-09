from datetime import date

from fakes import job, posting

from job_radar.matching import JobMatcher
from job_radar.model import Job, Search, SearchCriteria, Window
from job_radar.normalize import Normalizer
from job_radar.steps.filter import FilterStep

WINDOW = Window(start=date(2026, 10, 29), end=date(2026, 11, 5))
NO_ROLES = SearchCriteria(searches=(Search(name="default", roles=()),))


def step(*roles: str) -> FilterStep:
    return FilterStep(
        SearchCriteria(searches=(Search(name="default", roles=roles),)),
        WINDOW,
        JobMatcher(Normalizer()),
    )


def titles(jobs: list[Job]) -> list[str]:
    return [j.postings[0].title for j in jobs]


def test_a_run_keeps_only_postings_that_match_the_search_criteria():
    jobs = [
        job("1", "Senior Data Engineer"),
        job("2", "Product Designer"),
        job("3", "Data Analyst"),
    ]
    assert titles(step("data engineer", "analyst").run(jobs)) == [
        "Senior Data Engineer",
        "Data Analyst",
    ]


def test_roles_match_whole_words_in_any_case():
    jobs = [job("1", "International Programs Lead"), job("2", "Summer INTERN")]
    assert titles(step("intern").run(jobs)) == ["Summer INTERN"]


def test_roles_match_abbreviated_titles():
    assert titles(step("senior engineer").run([job("1", "Sr. Eng")])) == ["Sr. Eng"]


def test_no_roles_keeps_every_job():
    jobs = [job("1", "Anything"), job("2", "Something else")]
    assert FilterStep(NO_ROLES, WINDOW, JobMatcher(Normalizer())).run(jobs) == jobs


def test_filter_drops_jobs_posted_before_the_window():
    def dated(source_id: str, posted: date | None) -> Job:
        p = posting(source_id).model_copy(update={"posted_at": posted})
        return Job(id=p.key, keys=(p.key,), postings=(p,), first_seen=WINDOW.end)

    jobs = [dated("old", date(2026, 10, 28)), dated("first", WINDOW.start), dated("none", None)]
    kept = FilterStep(NO_ROLES, WINDOW, JobMatcher(Normalizer())).run(jobs)
    assert [j.id for j in kept] == ["demo:first", "demo:none"]


def test_a_job_matching_any_search_is_kept():
    criteria = SearchCriteria(
        searches=(
            Search(name="eng", roles=("engineer",)),
            Search(name="lead", roles=("tech lead",)),
        )
    )
    jobs = [job("1", "Tech Lead"), job("2", "Designer"), job("3", "Engineer")]
    kept = FilterStep(criteria, WINDOW, JobMatcher(Normalizer())).run(jobs)
    assert [j.postings[0].title for j in kept] == ["Tech Lead", "Engineer"]
