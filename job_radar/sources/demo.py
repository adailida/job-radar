"""A built-in job board with made-up postings, for trying the tool and for tests."""

import json
from datetime import date, timedelta

from job_radar.model import Posting, RawPage, SearchCriteria, Window
from job_radar.places import PlaceCodes


class DemoSource:
    """Serves the same made-up postings on every run, in pages, with no network.

    Used by `job-radar run --demo` and by the end-to-end tests. Plugs in like
    any real board, so the steps after it can't tell the difference. Postings
    are dated a set number of days before the window ends, so a run on any day
    finds the same ones. Stateless: the postings are fixed.
    """

    name = "demo"
    PAGE_SIZE = 7

    # id, title, company, location, work mode, yearly salary in USD (or None), days old
    POSTINGS = (
        ("1", "Senior Data Engineer", "Brightwater Trust", "New York, NY", "hybrid", (140, 170), 3),
        ("2", "Python Backend Engineer", "Open Harvest", "Remote, US", "remote", (120, 150), 4),
        ("3", "Product Designer", "Lanternfish Labs", "Boston, MA", "onsite", None, 6),
        ("4", "Platform Engineer", "Commons Ledger", "Remote, US", "remote", (130, 160), 0),
        ("5", "Data Analyst", "Riverbend Health", "Chicago, IL", "hybrid", (80, 95), 7),
        ("6", "Engineering Manager, Data Platform", "Brightwater Trust", "New York, NY", "hybrid", (180, 210), 3),
        ("7", "Grants Coordinator", "Open Harvest", "Denver, CO", "onsite", (55, 65), 5),
        ("8", "Machine Learning Engineer", "Northstar Climate", "Remote, US", "remote", (150, 185), 1),
        ("9", "Frontend Developer", "Lanternfish Labs", "Remote, US", "remote", None, 4),
        ("10", "Senior Python Developer", "Civic Signal", "Washington, DC", "hybrid", (135, 160), 3),
        ("11", "Operations Associate", "Riverbend Health", "Chicago, IL", "onsite", (50, 60), 8),
        ("12", "Data Engineer, APIs and Pipelines", "Northstar Climate", "Remote, US", "remote", (125, 145), 1),
    )  # fmt: skip

    def fetch(self, criteria: SearchCriteria, window: Window) -> list[RawPage]:
        """Return the made-up postings as pages of JSON, whatever the searches and window."""
        records = [self._record(*posting, window.end) for posting in self.POSTINGS]
        chunks = [records[i : i + self.PAGE_SIZE] for i in range(0, len(records), self.PAGE_SIZE)]
        return [
            RawPage(source=self.name, page=number, body=json.dumps({"jobs": chunk}))
            for number, chunk in enumerate(chunks, start=1)
        ]

    def _record(
        self,
        id: str,
        title: str,
        company: str,
        location: str,
        work_mode: str,
        salary: tuple[int, int] | None,
        days_old: int,
        end: date,
    ) -> dict:
        """One posting as the demo board sends it: already in the common posting shape."""
        slug = company.lower().replace(" ", "-")
        return {
            "source": self.name,
            "source_id": id,
            "title": title,
            "company": company,
            "locations": [{"text": location}],
            "work_mode": work_mode,
            "salary": None
            if salary is None
            else {
                "min": salary[0] * 1000,
                "max": salary[1] * 1000,
                "currency": "USD",
                "period": "year",
            },
            "url": f"https://example.org/{slug}/jobs/{id}",
            "posted_at": (end - timedelta(days=days_old)).isoformat(),
            "description": f"{company} is hiring a {title}. This posting is made up.",
        }


class DemoParser:
    """Turns the demo board's pages into postings, with place codes like a real board.

    Stateless: holds only how places are read.
    """

    source = "demo"

    def __init__(self, places: PlaceCodes) -> None:
        """Keep how places are read into codes."""
        self._places = places

    def parse(self, page: RawPage) -> list[Posting]:
        """Read the postings from one page of the demo board."""
        postings = [Posting.model_validate(record) for record in json.loads(page.body)["jobs"]]
        return [
            posting.model_copy(
                update={"locations": tuple(self._places.locate(p) for p in posting.locations)}
            )
            for posting in postings
        ]
