"""What the user is searching for, read from their `profile.yaml`."""

from pathlib import Path

from pydantic import Field

from job_radar.config.yaml_file import ConfigError, YamlFile
from job_radar.models import (
    Domains,
    MinSalary,
    Model,
    Places,
    Search,
    SearchCriteria,
    Seniorities,
    WorkModes,
)

DEMO_SEARCHES = SearchCriteria(
    searches=(
        Search(
            name="demo", roles=("engineer", "engineering", "developer", "tech lead", "architect")
        ),
    )
)
"""A made-up search for `job-radar run --demo` and the end-to-end tests."""


class _Criteria(Model):
    """The criteria of one search, as written in the file. An unset field comes from `common`."""

    roles: tuple[str, ...] | None = None
    exclude_titles: tuple[str, ...] | None = None
    work_mode: WorkModes | None = None
    locations: Places | None = None
    min_salary: MinSalary | None = None
    seniority: Seniorities | None = None
    domains: Domains | None = None


class _ProfileFile(Model):
    """The searches part of `profile.yaml`, as written."""

    common: _Criteria = _Criteria()  # applies to every search
    searches: dict[str, _Criteria] = Field(min_length=1)  # a job is wanted if any matches


class SearchesFile:
    """Reads the user's searches from `profile.yaml`.

    A field set in a search replaces the same field from `common`. Stateless:
    holds only the file.
    """

    def __init__(self, path: Path) -> None:
        """Keep the path of the user's `profile.yaml`."""
        self._path = path
        self._file = YamlFile(
            path, fix=f"Fix it in {path}; config/profile.example.yaml shows every key"
        )

    def load(self) -> SearchCriteria:
        """Every search in the file, with `common` filled in, in the file's order."""
        if not self._file.exists():
            raise ConfigError(
                f"no {self._path}: copy config/profile.example.yaml there and set your roles"
            )
        profile = self._file.load(_ProfileFile)
        return SearchCriteria(
            searches=tuple(
                self._search(name, criteria, profile.common)
                for name, criteria in profile.searches.items()
            )
        )

    @staticmethod
    def _search(name: str, own: _Criteria, common: _Criteria) -> Search:
        """One search: each field from the search if set there, else from `common`."""
        fields = {
            field: getattr(own, field)
            if getattr(own, field) is not None
            else getattr(common, field)
            for field in _Criteria.model_fields
        }
        return Search(
            name=name, **{key: value for key, value in fields.items() if value is not None}
        )
