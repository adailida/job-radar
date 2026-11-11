"""Keeping how requirements compare with a CV, so each is judged once per CV."""

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from job_radar.models import GapJudgment, Model, RequirementType

type RequirementKey = tuple[RequirementType, str]
"""A requirement as counted: its type and its name in one form."""


@runtime_checkable
class GapCache(Protocol):
    """Keeps how requirements compare with a CV, so each is judged once per CV (Repository)."""

    def judged(self, cv: str) -> dict[RequirementKey, GapJudgment]:
        """The judgments kept for the CV with this content hash; none for a new CV."""
        ...

    def add(self, cv: str, judged: dict[RequirementKey, GapJudgment]) -> None:
        """Keep these judgments for the CV with this content hash, over any kept before."""
        ...


class _Entry(Model):
    """One kept judgment: the CV it was made for, the requirement, and the judgment."""

    cv: str  # the CV's content hash
    type: RequirementType
    key: str  # the requirement's name in one form
    judgment: GapJudgment


class FileGapCache:
    """Keeps the CV comparison in one JSON Lines file outside the run folders.

    Deleting runs leaves it. Only one CV's judgments are kept: adding those of
    a new CV drops the old ones. A line that can't be read is skipped, so it
    is judged again. Holds only the file's path; the file is the state.
    """

    def __init__(self, path: Path) -> None:
        """Keep the path of the file."""
        self._path = path

    def judged(self, cv: str) -> dict[RequirementKey, GapJudgment]:
        """The judgments kept for this CV."""
        return {
            (entry.type, entry.key): entry.judgment for entry in self._entries() if entry.cv == cv
        }

    def add(self, cv: str, judged: dict[RequirementKey, GapJudgment]) -> None:
        """Write this CV's judgments with the new ones over them, through a temporary file."""
        kept = self.judged(cv) | judged
        lines = "".join(
            _Entry(cv=cv, type=kind, key=key, judgment=judgment).model_dump_json() + "\n"
            for (kind, key), judgment in kept.items()
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(self._path.name + ".tmp")
        temporary.write_text(lines, encoding="utf-8")
        os.replace(temporary, self._path)

    def _entries(self) -> list[_Entry]:
        """Every readable entry in the file; none when there is no file."""
        if not self._path.is_file():
            return []
        entries = []
        with self._path.open(encoding="utf-8") as lines:
            for line in lines:
                try:
                    entries.append(_Entry.model_validate_json(line))
                except ValidationError:
                    continue
        return entries
