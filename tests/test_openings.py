from datetime import date

import pytest
from fakes import grouper, posting

from job_radar.models import Classification, Job, Seniority


def labelled(
    source_id: str,
    job_type: str | None = None,
    domain: str | None = None,
    posted: int | None = 5,
    labels: bool = True,
) -> Job:
    """A job with these labels, posted on this day of November (None for undated)."""
    one = posting(source_id).model_copy(
        update={"posted_at": date(2026, 11, posted) if posted else None}
    )
    classification = Classification(
        job_id=one.key,
        seniority=Seniority.UNKNOWN,
        job_type=job_type,
        domain=domain,
        prompt_version="test",
    )
    return Job(
        id=one.key,
        keys=(one.key,),
        postings=(one,),
        first_seen=date(2026, 11, 9),
        classification=classification if labels else None,
    )


def shape(groups) -> list:
    """Each group's name with its job ids, or with the groups inside it."""
    return [
        (g.name, shape(g.groups) if g.groups else [o.job.id for o in g.openings]) for g in groups
    ]


def test_openings_are_grouped_by_job_type_in_the_settings_order():
    jobs = [labelled("1", "data"), labelled("2", "engineering"), labelled("3", "data")]
    assert shape(grouper("job_type").group(jobs, {})) == [
        ("engineering", ["demo:2"]),
        ("data", ["demo:1", "demo:3"]),
    ]


def test_openings_are_grouped_by_domain():
    jobs = [labelled("1", "data", "health"), labelled("2", "data", "climate")]
    assert shape(grouper("domain").group(jobs, {})) == [
        ("climate", ["demo:2"]),
        ("health", ["demo:1"]),
    ]


def test_grouped_by_both_each_job_type_holds_its_domains():
    jobs = [
        labelled("1", "engineering", "health"),
        labelled("2", "engineering", "climate"),
        labelled("3", "data", None),
        labelled("4", "engineering", "health"),
    ]
    groups = grouper("both").group(jobs, {})
    assert shape(groups) == [
        ("engineering", [("climate", ["demo:2"]), ("health", ["demo:1", "demo:4"])]),
        ("data", [("Not labelled", ["demo:3"])]),
    ]
    assert [g.size for g in groups] == [3, 1]


def test_openings_are_grouped_by_the_grouping_in_the_settings_and_other_goes_last():
    # A job type the settings don't name goes under "Other"; no label, or no labels at all,
    # under "Not labelled", after it. Empty groups are left out.
    jobs = [
        labelled("1", None),
        labelled("2", "Other"),
        labelled("3", "sales"),
        labelled("4", labels=False),
        labelled("5", "data"),
    ]
    assert shape(grouper("job_type").group(jobs, {})) == [
        ("data", ["demo:5"]),
        ("Other", ["demo:2", "demo:3"]),
        ("Not labelled", ["demo:1", "demo:4"]),
    ]


def test_within_a_group_the_newest_posted_come_first_and_undated_last():
    jobs = [
        labelled("1", "data", posted=3),
        labelled("2", "data", posted=None),
        labelled("3", "data", posted=8),
        labelled("4", "data", posted=3),
    ]
    assert shape(grouper().group(jobs, {})) == [("data", ["demo:3", "demo:1", "demo:4", "demo:2"])]


def test_a_recommended_job_keeps_its_score():
    jobs = [labelled("1", "data"), labelled("2", "data")]
    [group] = grouper().group(jobs, {"demo:2": 77})
    assert [(o.job.id, o.score) for o in group.openings] == [("demo:1", None), ("demo:2", 77)]


def test_no_jobs_means_no_groups():
    assert grouper("both").group([], {}) == ()


@pytest.mark.parametrize("group_by", ["job_type", "domain", "both"])
def test_every_grouping_keeps_every_job(group_by):
    jobs = [labelled(str(n), "data", "climate" if n % 2 else None) for n in range(6)]
    assert sum(g.size for g in grouper(group_by).group(jobs, {})) == 6
