"""Step 3: merge postings of the same job into one job."""

from datetime import date

from job_radar.model import Job, Posting
from job_radar.normalize import Normalizer


class JobKey:
    """Decides which postings describe the same job: same company, title and places.

    Compares names in canonical form, so "Acme, Inc." and "ACME" are one
    company. Places are compared as written, which merges less than comparing
    countries would, but never merges two cities. Stateless: holds only the
    normalizer.
    """

    # TODO(task 15): ATS keys from the URL, a fuzzy key on country, and keys from earlier runs.

    def __init__(self, normalizer: Normalizer) -> None:
        """Keep how names are put in canonical form."""
        self._normalize = normalizer

    def of(self, posting: Posting) -> str:
        """The key shared by every posting of the same job: "acme|senior data engineer|remote"."""
        texts = [place.text for place in posting.locations]
        places = sorted({self._normalize.place(text) for text in texts})
        company = self._normalize.company(posting.company)
        title = self._normalize.title(posting.title, texts)
        return f"{company}|{title}|{';'.join(places)}"


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
        return [self._job(key, group) for key, group in groups.items()]

    def _job(self, key: str, group: list[Posting]) -> Job:
        """One job from its postings, the most complete posting first.

        Most complete: the longest description, then one with a salary. The
        job keeps every posting's own key, so a merge can be traced.
        """
        postings = sorted(group, key=lambda p: (-len(p.description), p.salary is None))
        keys = (key, *(posting.key for posting in postings))
        return Job(id=key, keys=keys, postings=tuple(postings), first_seen=self._today)
