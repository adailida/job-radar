from datetime import date
from decimal import Decimal

import pytest

from job_radar.matching import JobMatcher
from job_radar.model import (
    IfMissing,
    Job,
    Location,
    MinSalary,
    Period,
    Places,
    Posting,
    Salary,
    Search,
    WorkMode,
    WorkModes,
)
from job_radar.normalize import Normalizer

MATCHER = JobMatcher(Normalizer())


def job(title="Software Engineer", mode=WorkMode.REMOTE, places=(), salary=None) -> Job:
    """A job of one posting with these fields."""
    posting = Posting(
        source="demo",
        source_id="1",
        title=title,
        company="Example Org",
        locations=tuple(places),
        work_mode=mode,
        salary=salary,
        url="https://example.org/jobs/1",
        description="",
    )
    return Job(id=posting.key, keys=(), postings=(posting,), first_seen=date(2026, 11, 9))


def place(country=None, region=None) -> Location:
    """A place with these codes."""
    return Location(text="somewhere", country=country, region=region)


def pay(low, high, currency="USD", period=Period.YEAR) -> Salary:
    """A salary range."""
    low, high = (None if v is None else Decimal(v) for v in (low, high))
    return Salary(min=low, max=high, currency=currency, period=period)


def test_a_job_meeting_every_criterion_matches():
    search = Search(
        name="s",
        roles=("engineer",),
        exclude_titles=("civil",),
        work_mode=WorkModes(values=(WorkMode.REMOTE,)),
        locations=Places(values=("US",)),
        min_salary=MinSalary(amount=Decimal(150000)),
    )
    found = job(places=[place("US")], salary=pay(140000, 170000))
    assert MATCHER.miss(found, search) is None


def test_names_the_first_criterion_a_job_fails():
    search = Search(name="s", roles=("engineer",), work_mode=WorkModes(values=(WorkMode.HYBRID,)))
    assert MATCHER.miss(job(title="Designer"), search) == "roles"
    assert MATCHER.miss(job(), search) == "work mode"


def test_excluded_titles_drop_whole_words_only():
    search = Search(name="s", exclude_titles=("civil",))
    assert MATCHER.miss(job(title="Civil Engineer"), search) == "excluded title"
    assert MATCHER.miss(job(title="Civilization Engineer"), search) is None


@pytest.mark.parametrize(
    ("mode", "if_missing", "kept"),
    [
        (WorkMode.REMOTE, IfMissing.DROP, True),
        (WorkMode.ONSITE, IfMissing.KEEP, False),
        (WorkMode.UNKNOWN, IfMissing.KEEP, True),
        (WorkMode.UNKNOWN, IfMissing.DROP, False),
    ],
)
def test_work_mode(mode, if_missing, kept):
    search = Search(name="s", work_mode=WorkModes(values=(WorkMode.REMOTE,), if_missing=if_missing))
    assert (MATCHER.miss(job(mode=mode), search) is None) == kept


@pytest.mark.parametrize(
    ("wanted", "places", "if_missing", "kept"),
    [
        (("US",), [place("US", "US-WA")], IfMissing.DROP, True),
        (("US-WA",), [place("US", "US-WA")], IfMissing.DROP, True),
        (("US-WA",), [place("US", "US-CA")], IfMissing.KEEP, False),
        (("US",), [place("UZ")], IfMissing.KEEP, False),
        (("US",), [place("UZ"), place("US")], IfMissing.DROP, True),
        (("US",), [place()], IfMissing.KEEP, True),
        (("US",), [place("IN"), place()], IfMissing.KEEP, False),
        (("US-WA",), [place("US"), place()], IfMissing.KEEP, True),
        (("US",), [place()], IfMissing.DROP, False),
        (("US",), [], IfMissing.KEEP, True),
        (("US",), [], IfMissing.DROP, False),
        (("US-WA",), [place("US")], IfMissing.KEEP, True),
        (("US-WA",), [place("US")], IfMissing.DROP, False),
        (("US-WA", "GB"), [place("GB")], IfMissing.DROP, True),
    ],
)
def test_locations(wanted, places, if_missing, kept):
    search = Search(name="s", locations=Places(values=wanted, if_missing=if_missing))
    assert (MATCHER.miss(job(places=places), search) is None) == kept


@pytest.mark.parametrize(
    ("salary", "if_missing", "kept"),
    [
        (pay(140000, 160000), IfMissing.DROP, True),
        (pay(100000, 140000), IfMissing.KEEP, False),
        (pay(150000, None), IfMissing.DROP, True),
        (pay(80, None, period=Period.HOUR), IfMissing.DROP, True),
        (pay(70, None, period=Period.HOUR), IfMissing.DROP, False),
        (pay(13000, None, period=Period.MONTH), IfMissing.DROP, True),
        (pay(200000, None, currency="EUR"), IfMissing.KEEP, True),
        (pay(200000, None, currency="EUR"), IfMissing.DROP, False),
        (None, IfMissing.KEEP, True),
        (None, IfMissing.DROP, False),
    ],
)
def test_salary(salary, if_missing, kept):
    search = Search(name="s", min_salary=MinSalary(amount=Decimal(150000), if_missing=if_missing))
    assert (MATCHER.miss(job(salary=salary), search) is None) == kept
