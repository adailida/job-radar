"""A built-in job board with made-up postings, for trying the tool and for tests."""

import json

from job_radar.model import Posting, RawPage, Search, Window


class DemoSource:
    """Serves the same made-up postings on every run, in pages, with no network.

    Used by `job-radar run --demo` and by the end-to-end tests. Plugs in like
    any real board, so the steps after it can't tell the difference. Stateless:
    the postings are fixed.
    """

    name = "demo"
    PAGE_SIZE = 7

    # id, title, company, location, work mode, yearly salary in USD (or None), posted
    POSTINGS = (
        ("1", "Senior Data Engineer", "Brightwater Trust", "New York, NY", "hybrid", (140, 170), "2026-11-02"),
        ("2", "Python Backend Engineer", "Open Harvest", "Remote, US", "remote", (120, 150), "2026-11-01"),
        ("3", "Product Designer", "Lanternfish Labs", "Boston, MA", "onsite", None, "2026-10-30"),
        ("4", "Platform Engineer", "Commons Ledger", "Remote, US", "remote", (130, 160), "2026-11-03"),
        ("5", "Data Analyst", "Riverbend Health", "Chicago, IL", "hybrid", (80, 95), "2026-10-29"),
        ("6", "Engineering Manager, Data Platform", "Brightwater Trust", "New York, NY", "hybrid", (180, 210), "2026-11-02"),
        ("7", "Grants Coordinator", "Open Harvest", "Denver, CO", "onsite", (55, 65), "2026-10-31"),
        ("8", "Machine Learning Engineer", "Northstar Climate", "Remote, US", "remote", (150, 185), "2026-11-03"),
        ("9", "Frontend Developer", "Lanternfish Labs", "Remote, US", "remote", None, "2026-11-01"),
        ("10", "Senior Python Developer", "Civic Signal", "Washington, DC", "hybrid", (135, 160), "2026-11-02"),
        ("11", "Operations Associate", "Riverbend Health", "Chicago, IL", "onsite", (50, 60), "2026-10-28"),
        ("12", "Data Engineer, APIs and Pipelines", "Northstar Climate", "Remote, US", "remote", (125, 145), "2026-11-04"),
    )  # fmt: skip

    def fetch(self, search: Search, window: Window) -> list[RawPage]:
        """Return the made-up postings as pages of JSON, whatever the search and window."""
        records = [self._record(*posting) for posting in self.POSTINGS]
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
        posted: str,
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
            "posted_at": posted,
            "description": f"{company} is hiring a {title}. This posting is made up.",
        }


class DemoParser:
    """Turns the demo board's pages into postings. Stateless."""

    source = "demo"

    def parse(self, page: RawPage) -> list[Posting]:
        """Read the postings from one page of the demo board."""
        return [Posting.model_validate(record) for record in json.loads(page.body)["jobs"]]
