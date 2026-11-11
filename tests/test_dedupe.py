from datetime import date
from decimal import Decimal

from fakes import posting

from job_radar.matching.ats_links import AtsLinks
from job_radar.matching.job_key import JobKey
from job_radar.matching.normalizer import Normalizer
from job_radar.models import Location, Period, Posting, Salary
from job_radar.pipeline.steps.dedupe import DedupeStep

KEY = JobKey(Normalizer(), AtsLinks())
TODAY = date(2026, 11, 5)
SALARY = Salary(min=Decimal(1), currency="USD", period=Period.YEAR)


def test_key_combines_company_title_and_places():
    assert (
        KEY.fuzzy(posting("1", "Sr. Data Eng (Remote)"))
        == "example org|senior data engineer|remote"
    )


def test_key_ignores_how_names_are_written():
    a = posting("1", "Senior Data Engineer").model_copy(update={"company": "Example Org, Inc."})
    b = posting("2", "Sr Data Eng (Remote)", source="other")
    assert KEY.fuzzy(a) == KEY.fuzzy(b)


def test_key_keeps_different_places_apart():
    oakland = posting("1").model_copy(update={"locations": (Location(text="Oakland, CA"),)})
    nyc = posting("2").model_copy(update={"locations": (Location(text="New York, NY"),)})
    assert KEY.fuzzy(oakland) != KEY.fuzzy(nyc)


def test_key_compares_countries_once_places_have_codes():
    def placed(source_id: str, text: str, country: str) -> Posting:
        location = Location(text=text, country=country)
        return posting(source_id).model_copy(update={"locations": (location,)})

    assert KEY.fuzzy(placed("1", "NYC", "US")) == KEY.fuzzy(placed("2", "New York, NY", "US"))
    assert KEY.fuzzy(placed("1", "Remote, US", "US")).endswith("|US")
    assert KEY.fuzzy(placed("1", "London", "GB")) != KEY.fuzzy(placed("2", "Boston", "US"))


def test_key_ignores_the_order_of_places():
    places = (Location(text="Remote"), Location(text="Oakland, CA"))
    a = posting("1").model_copy(update={"locations": places})
    b = posting("2").model_copy(update={"locations": places[::-1]})
    assert KEY.fuzzy(a) == KEY.fuzzy(b)


def test_two_postings_of_one_job_become_one_job():
    first = posting("1", "Senior Data Engineer", source="getro")
    second = posting("9", "Sr. Data Eng", source="jobspipe").model_copy(update={"salary": SALARY})
    other = posting("2", "Product Designer")
    jobs = DedupeStep(KEY, TODAY).run([first, other, second])
    assert len(jobs) == 2
    merged = jobs[0]
    assert merged.id == "example org|senior data engineer|remote"
    assert merged.keys == (merged.id, "jobspipe:9", "getro:1")
    assert merged.postings[0].salary == SALARY
    assert merged.first_seen == TODAY


def test_a_job_found_in_both_sources_appears_once():
    # Acceptance (Job search): a job found in both sources appears once.
    fast_forward = posting("1", "Senior Data Engineer", source="getro")
    jobspipe = posting("9", "Sr. Data Engineer", source="jobspipe").model_copy(
        update={"company": "Example Org, Inc."}
    )
    [job] = DedupeStep(KEY, TODAY).run([fast_forward, jobspipe])
    assert sorted(p.key for p in job.postings) == ["getro:1", "jobspipe:9"]


def test_primary_posting_has_the_longest_description():
    short = posting("1").model_copy(update={"description": "Short.", "salary": SALARY})
    long = posting("2", source="other").model_copy(update={"description": "Much longer text."})
    [job] = DedupeStep(KEY, TODAY).run([short, long])
    assert job.postings[0].key == "other:2"


def linked(source_id: str, title: str, url: str, source: str = "getro") -> Posting:
    """A posting with this title and link."""
    return posting(source_id, title, source=source).model_copy(update={"url": url})


GREENHOUSE = "https://boards.greenhouse.io/acme/jobs/42"


def test_postings_linking_to_one_ats_opening_merge_whatever_their_titles():
    a = linked("1", "Software Engineer III", GREENHOUSE)
    b = linked("9", "Software Engineer, Platform", GREENHOUSE + "?gh_src=x", source="jobspipe")
    [job] = DedupeStep(KEY, TODAY).run([a, b])
    assert job.id == "greenhouse:acme:42"
    assert job.keys[:3] == (
        "greenhouse:acme:42",
        "example org|software engineer iii|remote",
        "example org|software engineer platform|remote",
    )


def test_postings_sharing_any_key_merge_transitively():
    a = linked("1", "Data Engineer", GREENHOUSE)
    b = linked("2", "Senior Data Engineer", GREENHOUSE, source="jobspipe")
    c = posting("3", "Sr. Data Eng", source="other")
    d = posting("4", "Designer")
    jobs = DedupeStep(KEY, TODAY).run([c, d, a, b])
    assert [sorted(p.key for p in j.postings) for j in jobs] == [
        ["getro:1", "jobspipe:2", "other:3"],
        ["demo:4"],
    ]


def test_a_job_without_an_ats_link_is_known_by_its_fuzzy_key():
    [job] = DedupeStep(KEY, TODAY).run([posting("1", "Data Engineer")])
    assert job.id == "example org|data engineer|remote"
