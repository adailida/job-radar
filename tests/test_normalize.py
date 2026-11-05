import pytest

from job_radar.normalize import Normalizer

NORMALIZE = Normalizer()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Acme, Inc.", "acme"),
        ("ACME", "acme"),
        ("Acme Corp", "acme"),
        ("Example Org GmbH", "example org"),
        ("Inc", "inc"),
        ("Fundação Ação", "fundacao acao"),
    ],
)
def test_company_names(name, expected):
    assert NORMALIZE.company(name) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Sr. Data Eng (Remote, US)", "senior data engineer"),
        ("Senior Data Engineer", "senior data engineer"),
        ("Jr Dev [Hybrid]", "junior developer"),
        (
            "Capacity Building Specialist (Media and Communication)",
            "capacity building specialist media and communication",
        ),
        ("Research Software Engineer [UK-2026-RSE-1", "research software engineer uk 2026 rse 1"),
        ("Engineering Manager", "engineering manager"),
    ],
)
def test_titles(title, expected):
    assert NORMALIZE.title(title) == expected


def test_title_drops_an_aside_naming_the_postings_own_place():
    assert (
        NORMALIZE.title("Field Officer (Kaloleni, Kenya)", ["Kaloleni, Kenya"]) == "field officer"
    )
    assert NORMALIZE.title("Field Officer (Kaloleni, Kenya)") == "field officer kaloleni kenya"


def test_places():
    assert NORMALIZE.place("São Paulo, Brazil") == "sao paulo brazil"
