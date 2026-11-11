"""What the user is looking for: the searches and their criteria, and the CV and preferences."""

import re
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from job_radar.models.llm import Seniority
from job_radar.models.model import Model
from job_radar.models.posting import Period, WorkMode


class IfMissing(StrEnum):
    """What a criterion does with a job that doesn't say: keep it or drop it."""

    KEEP = "keep"
    DROP = "drop"


class _Criterion(Model):
    """Base for criteria a posting may not say anything about.

    Written in full (`{values: [...], if_missing: drop}`) or short, as just the
    list of values, which keeps jobs that don't say.
    """

    if_missing: IfMissing = IfMissing.KEEP

    @model_validator(mode="before")
    @classmethod
    def _short_form(cls, data: object) -> object:
        """Read a bare list as the values, keeping jobs that don't say."""
        return {"values": data} if isinstance(data, list | tuple) else data


class WorkModes(_Criterion):
    """The work modes wanted: a job matches if it has any of them."""

    values: tuple[WorkMode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _known_modes(self) -> Self:
        """Unknown is what a missing work mode is, not a mode to ask for."""
        if WorkMode.UNKNOWN in self.values:
            raise ValueError("work modes are remote, hybrid or onsite")
        return self


class Places(_Criterion):
    """The places wanted, as ISO codes: `US` is anywhere in the US, `US-WA` is Washington only."""

    values: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _iso_codes(self) -> Self:
        """Each value is a country code, optionally with a region: `US`, `US-WA`."""
        bad = [v for v in self.values if not re.fullmatch(r"[A-Z]{2}(-[A-Z0-9]{1,3})?", v)]
        if bad:
            raise ValueError(f"not ISO codes like US or US-WA: {', '.join(bad)}")
        return self


class MinSalary(_Criterion):
    """The lowest pay wanted. A job meets it if the top of its range does."""

    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    period: Period = Period.YEAR

    @model_validator(mode="before")
    @classmethod
    def _short_form(cls, data: object) -> object:
        """Read a bare number as a yearly amount in USD, keeping jobs that don't say."""
        return {"amount": data} if isinstance(data, int | float | str | Decimal) else data


class Seniorities(_Criterion):
    """The levels wanted: a job matches if its seniority is any of them. Unknown is missing."""

    values: tuple[Seniority, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _known_levels(self) -> Self:
        """Unknown is what a missing level is, not a level to ask for."""
        if Seniority.UNKNOWN in self.values:
            raise ValueError("ask for levels such as senior or lead; unknown is if_missing's job")
        return self


class Domains(_Criterion):
    """The domains wanted, by name from the settings: a job matches if its domain is any of them."""

    values: tuple[str, ...] = Field(min_length=1)


class Search(Model):
    """One named search: criteria a job must meet together. An unset criterion lets every job by."""

    # TODO(task 11c): keywords in the description, checked after the describe step.
    name: str
    roles: tuple[str, ...] = ()  # the title contains any, as whole words
    exclude_titles: tuple[str, ...] = ()  # the title contains none, as whole words
    work_mode: WorkModes | None = None
    locations: Places | None = None
    min_salary: MinSalary | None = None
    seniority: Seniorities | None = None  # checked once the job is classified
    domains: Domains | None = None  # checked once the job is classified


class SearchCriteria(Model):
    """All of the user's searches. A job is wanted if it matches any of them."""

    searches: tuple[Search, ...]


class CandidateProfile(Model):
    """What a good job is for the user: their CV and their ideal job in their own words."""

    cv: str  # text taken from the CV file
    preferences: str  # free text
