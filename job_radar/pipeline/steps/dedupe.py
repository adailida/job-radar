"""Step 3: merge postings of the same job into one job."""

from datetime import date

from job_radar.matching.job_key import JobKey
from job_radar.models import Job, Posting


class DedupeStep:
    """Groups postings of the same job into one `Job`, by any key they share.

    Stateless: holds only the rule for "same job" and the date of the run.
    """

    name = "dedupe"
    output = Job

    def __init__(self, key: JobKey, today: date) -> None:
        """Keep the rule that decides which postings are the same job, and the run's date."""
        self._key = key
        self._today = today

    def run(self, data: list[Posting]) -> list[Job]:
        """Group postings that share any key, transitively; one job per group, first seen first.

        A and B sharing an ATS key and B and C a fuzzy key makes one job of all three.
        """
        parent = list(range(len(data)))  # each posting's group, by the position of its first
        first: dict[str, int] = {}  # each key, and the first posting that had it
        for index, posting in enumerate(data):
            for key in self._key.keys(posting):
                if key in first:
                    a, b = self._root(parent, index), self._root(parent, first[key])
                    parent[max(a, b)] = min(a, b)
                else:
                    first[key] = index
        groups: dict[int, list[Posting]] = {}
        for index, posting in enumerate(data):
            groups.setdefault(self._root(parent, index), []).append(posting)
        return [self._job(group) for group in groups.values()]

    @staticmethod
    def _root(parent: list[int], index: int) -> int:
        """The first posting of the group this one belongs to."""
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def _job(self, group: list[Posting]) -> Job:
        """One job from its postings, the most complete posting first.

        Most complete: the longest description, then one with a salary. The
        job's id is the primary posting's strongest key; the job keeps every
        identity key and every posting's own key, so a merge can be traced.
        """
        postings = sorted(group, key=lambda p: (-len(p.description), p.salary is None))
        identity = list(dict.fromkeys(key for p in postings for key in self._key.keys(p)))
        primary = self._key.keys(postings[0])[0]
        keys = (*identity, *(posting.key for posting in postings))
        return Job(id=primary, keys=keys, postings=tuple(postings), first_seen=self._today)
