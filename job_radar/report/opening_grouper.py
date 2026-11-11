"""Putting this run's new matched jobs under the report's headings."""

from collections.abc import Mapping, Sequence
from datetime import date

from job_radar.models import Job, Opening, OpeningGroup


class OpeningGrouper:
    """Sorts new matched jobs into groups by their job type, their domain, or both.

    Groups follow the order the settings list them in, then "Other" (a label
    the settings don't have), then "Not labelled" (no label, or no labels at
    all); empty groups are left out. Grouped by both, each job type holds its
    domains. Within a group, the newest posted come first, undated last.
    Stateless: holds only what to group by and the names in settings order.
    """

    OTHER = "Other"
    NOT_LABELLED = "Not labelled"
    LEVELS = {"job_type": ("job_type",), "domain": ("domain",), "both": ("job_type", "domain")}

    def __init__(self, group_by: str, job_types: Sequence[str], domains: Sequence[str]) -> None:
        """Keep what to group by (job_type, domain or both) and the names, in settings order."""
        self._levels = self.LEVELS[group_by]
        self._names = {"job_type": tuple(job_types), "domain": tuple(domains)}

    def group(self, jobs: Sequence[Job], scores: Mapping[str, int]) -> tuple[OpeningGroup, ...]:
        """The jobs in their groups, each with its score when it has one, by job id."""
        newest = sorted(jobs, key=self._posted, reverse=True)
        openings = [Opening(job=job, score=scores.get(job.id)) for job in newest]
        return self._split(openings, self._levels)

    def _split(
        self, openings: Sequence[Opening], levels: Sequence[str]
    ) -> tuple[OpeningGroup, ...]:
        """The openings under the first level's names, split again by any level after it."""
        label, rest = levels[0], levels[1:]
        names = self._names[label]
        buckets: dict[str, list[Opening]] = {
            name: [] for name in (*names, self.OTHER, self.NOT_LABELLED)
        }
        for opening in openings:
            buckets[self._name(opening.job, label, names)].append(opening)
        return tuple(
            OpeningGroup(name=name, groups=self._split(inside, rest))
            if rest
            else OpeningGroup(name=name, openings=tuple(inside))
            for name, inside in buckets.items()
            if inside
        )

    def _name(self, job: Job, label: str, names: Sequence[str]) -> str:
        """The group a job goes in for one label: its name, "Other" or "Not labelled"."""
        value = getattr(job.classification, label) if job.classification else None
        if value is None:
            return self.NOT_LABELLED
        return value if value in names else self.OTHER

    @staticmethod
    def _posted(job: Job) -> date:
        """The sort key: the primary posting's date, undated jobs as the oldest."""
        return job.postings[0].posted_at or date.min
