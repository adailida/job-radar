"""Step 3: merge postings of the same job into one job."""

from job_radar.model import Job, Posting


class JobKey:
    """Decides which postings describe the same job. Stateless."""

    def of(self, posting: Posting) -> str:
        """The key shared by every posting of the same job."""
        # TODO(task 6): normalize company, title and location.
        raise NotImplementedError


class DedupeStep:
    """Groups postings of the same job into one `Job`.

    Stateless: holds only the rule for "same job".
    """

    name = "dedupe"
    output = Job

    def __init__(self, key: JobKey) -> None:
        """Keep the rule that decides which postings are the same job."""
        self._key = key

    def run(self, data: list[Posting]) -> list[Job]:
        """Group the postings by key, one job per group."""
        # TODO(task 6): group by key.
        raise NotImplementedError
