from datetime import date
from decimal import Decimal

from fakes import posting

from job_radar.model import Location, Period, Salary
from job_radar.normalize import Normalizer
from job_radar.steps.dedupe import DedupeStep, JobKey

KEY = JobKey(Normalizer())
TODAY = date(2026, 11, 5)
SALARY = Salary(min=Decimal(1), currency="USD", period=Period.YEAR)


def test_key_combines_company_title_and_places():
    assert (
        KEY.of(posting("1", "Sr. Data Eng (Remote)")) == "example org|senior data engineer|remote"
    )


def test_key_ignores_how_names_are_written():
    a = posting("1", "Senior Data Engineer").model_copy(update={"company": "Example Org, Inc."})
    b = posting("2", "Sr Data Eng (Remote)", source="other")
    assert KEY.of(a) == KEY.of(b)


def test_key_keeps_different_places_apart():
    oakland = posting("1").model_copy(update={"locations": (Location(text="Oakland, CA"),)})
    nyc = posting("2").model_copy(update={"locations": (Location(text="New York, NY"),)})
    assert KEY.of(oakland) != KEY.of(nyc)


def test_key_ignores_the_order_of_places():
    places = (Location(text="Remote"), Location(text="Oakland, CA"))
    a = posting("1").model_copy(update={"locations": places})
    b = posting("2").model_copy(update={"locations": places[::-1]})
    assert KEY.of(a) == KEY.of(b)


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


def test_primary_posting_has_the_longest_description():
    short = posting("1").model_copy(update={"description": "Short.", "salary": SALARY})
    long = posting("2", source="other").model_copy(update={"description": "Much longer text."})
    [job] = DedupeStep(KEY, TODAY).run([short, long])
    assert job.postings[0].key == "other:2"
