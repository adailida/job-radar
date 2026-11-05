"""Step 3: merge postings of the same job into one job."""

from datetime import date

from job_radar.model import Job, Posting


class JobKey:
    """Decides which postings describe the same job. Stateless."""

    def of(self, posting: Posting) -> str:
        """The key shared by every posting of the same job."""
        # TODO(task 6): normalize company, title and location; for now only exact repeats merge.
        return posting.key


class DedupeStep:
    """Groups postings of the same job into one `Job`.

    Stateless: holds only the rule for "same job" and the date of the run.
    """

    name = "dedupe"
    output = Job

    def __init__(self, key: JobKey, today: date) -> None:
        """Keep the rule that decides which postings are the same job, and the run's date."""
        self._key = key
        self._today = today

    def run(self, data: list[Posting]) -> list[Job]:
        """Group the postings by key, one job per group, in the order first seen."""
        groups: dict[str, list[Posting]] = {}
        for posting in data:
            groups.setdefault(self._key.of(posting), []).append(posting)
        return [
            Job(id=key, keys=(key,), postings=tuple(group), first_seen=self._today)
            for key, group in groups.items()
        ]
