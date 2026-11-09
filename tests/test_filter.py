from datetime import date

from fakes import MemoryDropLog, job, posting

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
        MemoryDropLog(),
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
    assert FilterStep(NO_ROLES, WINDOW, JobMatcher(Normalizer()), MemoryDropLog()).run(jobs) == jobs


def dated(source_id: str, posted: date | None) -> Job:
    """A job of one posting, posted on this day."""
    p = posting(source_id).model_copy(update={"posted_at": posted})
    return Job(id=p.key, keys=(p.key,), postings=(p,), first_seen=WINDOW.end)


def test_filter_drops_jobs_posted_before_the_window():
    jobs = [dated("old", date(2026, 10, 28)), dated("first", WINDOW.start), dated("none", None)]
    kept = FilterStep(NO_ROLES, WINDOW, JobMatcher(Normalizer()), MemoryDropLog()).run(jobs)
    assert [j.id for j in kept] == ["demo:first", "demo:none"]


def test_a_job_matching_any_search_is_kept():
    criteria = SearchCriteria(
        searches=(
            Search(name="eng", roles=("engineer",)),
            Search(name="lead", roles=("tech lead",)),
        )
    )
    jobs = [job("1", "Tech Lead"), job("2", "Designer"), job("3", "Engineer")]
    kept = FilterStep(criteria, WINDOW, JobMatcher(Normalizer()), MemoryDropLog()).run(jobs)
    assert [j.postings[0].title for j in kept] == ["Tech Lead", "Engineer"]


def test_lists_each_dropped_job_with_why_for_every_search():
    criteria = SearchCriteria(
        searches=(
            Search(name="eng", roles=("engineer",)),
            Search(name="lead", roles=("tech lead",), exclude_titles=("intern",)),
        )
    )
    log = MemoryDropLog()
    jobs = [
        job("1", "Engineer"),
        job("2", "Designer"),
        dated("old", date(2026, 10, 1)),
        job("3", "Tech Lead Intern"),
    ]
    kept = FilterStep(criteria, WINDOW, JobMatcher(Normalizer()), log).run(jobs)
    assert [j.id for j in kept] == ["demo:1"]
    assert (log.drops.checked, log.drops.kept, log.drops.before_window) == (4, 1, 1)
    assert [(d.job.id, d.reasons) for d in log.drops.dropped] == [
        ("demo:2", ("eng: roles", "lead: roles")),
        ("demo:3", ("eng: roles", "lead: excluded title")),
    ]
