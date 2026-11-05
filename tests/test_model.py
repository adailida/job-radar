from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from job_radar.clock import Clock
from job_radar.model import (
    CandidateProfile,
    Classification,
    Extraction,
    Job,
    Location,
    Match,
    Period,
    Posting,
    RawPage,
    Recommendation,
    Report,
    Requirement,
    RequirementType,
    Salary,
    Seniority,
    StepCount,
    Window,
    WorkMode,
)

POSTING = Posting(
    source="getro",
    source_id="123",
    title="Software Engineer",
    company="Example Org",
    locations=(Location(text="New York, NY", country="US", region="US-NY"),),
    work_mode=WorkMode.HYBRID,
    salary=Salary(
        min=Decimal("120000"),
        max=Decimal("150000.50"),
        currency="USD",
        period=Period.YEAR,
        text="$120k to $150k",
    ),
    url="https://example.org/jobs/123",
    posted_at=date(2026, 11, 2),
    description="Build things.",
)

SPARSE_POSTING = Posting(
    source="jobspipe",
    source_id="abc",
    title="Data Analyst",
    company="Another Org",
    locations=(Location(text="Anywhere"),),
    work_mode=WorkMode.UNKNOWN,
    salary=None,
    url="https://example.com/a",
    posted_at=None,
    description="",
)

JOB = Job(
    id="getro:123",
    keys=("getro:123", "greenhouse:exampleorg:456"),
    postings=(POSTING, SPARSE_POSTING),
    first_seen=date(2026, 11, 3),
)

CLASSIFICATION = Classification(
    job_id="getro:123",
    seniority=Seniority.MID,
    job_type="Engineering",
    domain=None,
    sector="Nonprofit",
    prompt_version="classify-v1",
)

EXTRACTION = Extraction(
    job_id="getro:123",
    requirements=(
        Requirement(type=RequirementType.SKILL, name="Python"),
        Requirement(type=RequirementType.YEARS, name="Python", years=5),
    ),
    prompt_version="extract-v1",
)

MATCH = Match(job_id="getro:123", searches=("remote-us", "onsite-ny"))

RAW_PAGE = RawPage(source="getro", page=1, body='{"jobs": []}')

PROFILE = CandidateProfile(cv="Ten years of Python.", preferences="Small team, remote.")

RECOMMENDATION = Recommendation(job=JOB, score=87, reason="Python and remote, as preferred.")

REPORT = Report(location="output/runs/2026-11-05T10-00/report.md", summary="12 from 340")

STEP_COUNT = StepCount(step="convert", count=340)

SAMPLES = [
    RAW_PAGE,
    POSTING,
    SPARSE_POSTING,
    JOB,
    CLASSIFICATION,
    EXTRACTION,
    MATCH,
    PROFILE,
    RECOMMENDATION,
    REPORT,
    STEP_COUNT,
]


@pytest.mark.parametrize("model", SAMPLES, ids=lambda m: type(m).__name__)
def test_models_round_trip_to_json(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model


def test_models_are_frozen():
    with pytest.raises(ValidationError):
        JOB.id = "other"
    with pytest.raises(AttributeError):
        JOB.postings.append(POSTING)


def test_lists_are_stored_as_tuples():
    match = Match(job_id="j", searches=["a", "b"])
    assert match.searches == ("a", "b")


def test_unknown_field_rejected():
    data = POSTING.model_dump(mode="json") | {"titel": "Typo"}
    with pytest.raises(ValidationError, match="titel"):
        Posting.model_validate(data)


def test_window_start_after_end_rejected():
    with pytest.raises(ValidationError, match="start"):
        Window(start=date(2026, 11, 3), end=date(2026, 11, 2))


def test_posting_key():
    assert POSTING.key == "getro:123"


def test_recommendation_score_out_of_range_rejected():
    with pytest.raises(ValidationError, match="score"):
        Recommendation(job=JOB, score=101, reason="")


def test_now_is_timezone_aware():
    assert Clock().now().tzinfo is not None
