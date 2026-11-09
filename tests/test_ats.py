import pytest

from job_radar.ats import AtsLinks


@pytest.mark.parametrize(
    ("url", "key"),
    [
        (
            "https://boards.greenhouse.io/recidiviz/jobs/4664444006",
            "greenhouse:recidiviz:4664444006",
        ),
        (
            "https://job-boards.greenhouse.io/Acme/jobs/123?gh_src=abc&utm_source=x",
            "greenhouse:acme:123",
        ),
        (
            "https://jobs.lever.co/acme/6f1c2b9e-1234-4abc-9def-0123456789ab/apply",
            "lever:acme:6f1c2b9e-1234-4abc-9def-0123456789ab",
        ),
        (
            "https://jobs.ashbyhq.com/educationsuperhighway/de14b051-52de-4e20-aa70-4be632839007",
            "ashby:educationsuperhighway:de14b051-52de-4e20-aa70-4be632839007",
        ),
        ("https://apply.workable.com/acme/j/AB12CD34EF/", "workable:acme:ab12cd34ef"),
        ("https://www.linkedin.com/jobs/view/4483209310", None),
        ("https://boards.greenhouse.io/acme", None),
        ("not a link", None),
    ],
)
def test_reads_the_openings_key_from_a_known_ats_link(url, key):
    assert AtsLinks().key(url) == key
