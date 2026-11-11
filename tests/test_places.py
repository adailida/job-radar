import pytest

from job_radar.matching.place_codes import PlaceCodes
from job_radar.models import Location


@pytest.mark.parametrize(
    ("text", "country", "region"),
    [
        ("Seattle, WA, USA", "US", "US-WA"),
        ("Colorado, USA", "US", "US-CO"),
        ("Washington, DC, USA", "US", "US-DC"),
        ("United States", "US", None),
        ("Remote, US", "US", None),
        ("New York, NY", "US", "US-NY"),
        ("London, UK", "GB", None),
        ("Zürich, Switzerland", "CH", "CH-ZH"),
        ("Lukula, Democratic Republic of the Congo", "CD", None),
        ("brasília - brasilia, federal district, brazil", "BR", None),
        ("Hong Kong", "HK", None),
        ("Yangon, Myanmar (Burma)", "MM", "MM-06"),
        ("Remote", None, None),
        ("", None, None),
    ],
)
def test_reads_country_and_region_codes_from_the_text(text, country, region):
    located = PlaceCodes().locate(Location(text=text))
    assert (located.text, located.country, located.region) == (text, country, region)
