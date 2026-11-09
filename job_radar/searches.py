"""What the user is searching for, read from their `profile.yaml`."""

from pathlib import Path

from pydantic import Field

from job_radar.model import Model, Search, SearchCriteria
from job_radar.yaml_file import ConfigError, YamlFile

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

    # TODO(task 11): locations, work mode, keywords, excluded titles, salary, if_missing.
    roles: tuple[str, ...] | None = None  # the title contains any of them


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
        self._file = YamlFile(path)

    def load(self) -> SearchCriteria:
        """Every search in the file, with `common` filled in, in the file's order."""
        if not self._file.exists():
            raise ConfigError(
                f"no {self._path}: copy examples/profile.example.yaml there and set your roles"
            )
        profile = self._file.load(_ProfileFile)
        return SearchCriteria(
            searches=tuple(
                Search(name=name, roles=self._pick(criteria.roles, profile.common.roles))
                for name, criteria in profile.searches.items()
            )
        )

    @staticmethod
    def _pick(own: tuple[str, ...] | None, common: tuple[str, ...] | None) -> tuple[str, ...]:
        """The search's own value if set, else the common one, else none."""
        return own if own is not None else (common or ())
