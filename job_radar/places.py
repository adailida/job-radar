"""Turning a board's free-text places into country and region codes."""

import re

import pycountry

from job_radar.model import Location


class PlaceCodes:
    """Reads ISO codes from a place as boards write it, such as "Seattle, WA, USA".

    The country is the last part ("USA", "London, UK"); a place that ends in a
    US state, like "New York, NY", is in the US. The region is any other part
    that names one of the country's subdivisions, by code or by name. A place
    with no country it can read ("Remote") gets no codes. Stateless.
    """

    ALIASES = {
        "uk": "GB",
        "england": "GB",
        "scotland": "GB",
        "wales": "GB",
        "northern ireland": "GB",
        "democratic republic of the congo": "CD",
        "drc": "CD",
        "south korea": "KR",
        "russia": "RU",
        "vietnam": "VN",
        "turkey": "TR",
    }

    def locate(self, location: Location) -> Location:
        """The location with its country and region filled in when the text names them."""
        parts = [part.strip() for part in location.text.split(",") if part.strip()]
        if not parts:
            return location
        country = self._country(parts[-1])
        rest = parts[:-1]
        if country is None and self._us_region(parts[-1]):
            country, rest = "US", parts
        if country is None:
            return location
        region = next(
            (code for part in reversed(rest) if (code := self._region(country, part))), None
        )
        return location.model_copy(update={"country": country, "region": region})

    def _country(self, text: str) -> str | None:
        """The country code a name or code stands for, or None.

        A name with an aside in brackets ("Myanmar (Burma)") is also tried
        without it.
        """
        for name in dict.fromkeys((text, re.sub(r"\s*\([^)]*\)\s*$", "", text))):
            alias = self.ALIASES.get(name.lower())
            if alias:
                return alias
            try:
                return pycountry.countries.lookup(name).alpha_2
            except LookupError:
                continue
        return None

    def _us_region(self, text: str) -> str | None:
        """The US state a code or name stands for ("WA", "Washington"), or None."""
        return self._region("US", text)

    @staticmethod
    def _region(country: str, text: str) -> str | None:
        """The code of the country's subdivision this text names, by code or name, or None."""
        subdivisions = pycountry.subdivisions.get(country_code=country) or []
        wanted = text.casefold()
        for subdivision in subdivisions:
            if subdivision.code.split("-", 1)[1] == text or subdivision.name.casefold() == wanted:
                return subdivision.code
        return None
