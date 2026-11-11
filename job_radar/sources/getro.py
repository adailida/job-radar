"""Job boards hosted on Getro, such as Fast Forward's."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from job_radar.matching.place_codes import PlaceCodes
from job_radar.models import (
    Location,
    Period,
    Posting,
    RawPage,
    Salary,
    SearchCriteria,
    Window,
    WorkMode,
)
from job_radar.sources.board_client import BoardClient
from job_radar.utils.html_text import HtmlText
from job_radar.utils.progress import NoProgress, Progress


class GetroSource:
    """Pages through a Getro board's job search, newest jobs first.

    The search has no date filter, so paging stops at the first page that
    reaches back past the window's start; the filter step drops the older jobs
    on that page. A board that fails part way fails as a whole, so a fetch is
    never partial. Says which page it is on as it goes. Stateless: holds only the board, its
    client and who it tells.
    """

    name = "getro"
    SEARCH = "https://api.getro.com/api/v2/collections/{network}/search/jobs"
    PAGE_SIZE = 200  # the most the search returns per page
    BOARDS = {"997": "Fast Forward"}  # the boards known by name, by network id

    def __init__(self, network: str, client: BoardClient, progress: Progress | None = None) -> None:
        """Keep the board's network id, the client that paces and retries requests, who is told."""
        self._network = network
        self._client = client
        self._progress = progress or NoProgress()

    @property
    def label(self) -> str:
        """The board's name for people: "Fast Forward", or "Getro board 123" for one not known."""
        return self.BOARDS.get(self._network, f"Getro board {self._network}")

    def fetch(self, criteria: SearchCriteria, window: Window) -> list[RawPage]:
        """Fetch pages, newest jobs first, until one reaches back past the window's start.

        The searches aren't sent: the whole window is small enough to
        fetch, and the filter step applies the criteria to every board alike.
        """
        pages: list[RawPage] = []
        so_far = 0
        while True:
            if pages:
                self._client.pause()
            self._progress.detail(f"{self.label} page {len(pages) + 1}, {so_far} jobs so far")
            body = self._page(len(pages))
            pages.append(RawPage(source=self.name, page=len(pages) + 1, body=body))
            results = json.loads(body)["results"]
            jobs = results["jobs"]
            so_far += len(jobs)
            fetched = (len(pages) - 1) * self.PAGE_SIZE + len(jobs)
            if not jobs or fetched >= results["count"] or self._oldest(jobs) < window.start:
                return pages

    def _page(self, index: int) -> str:
        """One page of the search, numbered from 0."""
        query = {"hits_per_page": self.PAGE_SIZE, "page": index, "filters": "", "query": ""}
        url = self.SEARCH.format(network=self._network)
        response = self._client.post(url, json=query, headers={"Accept": "application/json"})
        return self._client.check(response).text

    def _oldest(self, jobs: list[dict]) -> date:
        """The day the oldest job on a page was listed."""
        return GetroParser.listed_on(min(job["created_at"] for job in jobs))


class GetroParser:
    """Turns pages of a Getro board's job search into postings.

    Places get country and region codes when their text names them.
    Stateless: holds only how places are read.
    """

    source = "getro"
    WORK_MODES = {"on_site": WorkMode.ONSITE, "hybrid": WorkMode.HYBRID, "remote": WorkMode.REMOTE}
    PERIODS = {"year": Period.YEAR, "month": Period.MONTH, "hour": Period.HOUR}

    def __init__(self, places: PlaceCodes) -> None:
        """Keep how places are read into codes."""
        self._places = places

    def parse(self, page: RawPage) -> list[Posting]:
        """Convert one page of search results into postings."""
        return [self._posting(job) for job in json.loads(page.body)["results"]["jobs"]]

    @staticmethod
    def listed_on(created_at: int) -> date:
        """The day a job was listed on the board, from the search's timestamp (UTC)."""
        return datetime.fromtimestamp(created_at, UTC).date()

    def _posting(self, job: dict) -> Posting:
        """One search result as a posting. `GetroDescriber` adds the description, for jobs kept."""
        return Posting(
            source=self.source,
            source_id=str(job["id"]),
            title=job["title"].strip(),
            company=job["organization"]["name"],
            locations=tuple(self._places.locate(Location(text=text)) for text in job["locations"]),
            work_mode=self.WORK_MODES.get(job["work_mode"], WorkMode.UNKNOWN),
            salary=self._salary(job),
            url=job["url"],
            posted_at=self.listed_on(job["created_at"]),
            description="",
        )

    def _salary(self, job: dict) -> Salary | None:
        """The pay range when the board shows one with a currency and a period."""
        low, high = job["compensation_amount_min_cents"], job["compensation_amount_max_cents"]
        currency = job["compensation_currency"]
        period = self.PERIODS.get(job["compensation_period"])
        if not job["compensation_public"] or (low is None and high is None):
            return None
        if currency is None or period is None:
            return None
        return Salary(
            min=None if low is None else Decimal(low) / 100,
            max=None if high is None else Decimal(high) / 100,
            currency=currency,
            period=period,
        )


class GetroDescriber:
    """Fetches the full description of one job on a Getro board, as plain text.

    The search leaves descriptions out, so each one is a request of its own.
    Pauses before every request, so calls in a row keep the board's pace. A
    job the board no longer has, or no longer lists as active, gets no
    description; any other error fails. Stateless: holds only the board, its
    client and how HTML becomes text.
    """

    source = "getro"
    JOB = "https://api.getro.com/api/v1/jobs/{id}"

    def __init__(self, network: str, client: BoardClient, html: HtmlText) -> None:
        """Keep the board's network id, the client, and how to turn HTML into text."""
        self._network = network
        self._client = client
        self._html = html

    @property
    def pace(self) -> float:
        """Seconds each description takes at least: the pause before its request."""
        return self._client.delay

    def describe(self, posting: Posting) -> str:
        """The job's description as plain text; empty when the board has none for it."""
        self._client.pause()
        response = self._client.get(
            self.JOB.format(id=posting.source_id),
            params={"collection_id": self._network},
            headers={"Accept": "application/json"},
        )
        if response.status_code == 404:
            return ""
        job = self._client.check(response).json()
        if job["status"] != "active":
            return ""
        return self._html.text(job["description"] or "")
