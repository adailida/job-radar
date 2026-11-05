"""Job boards hosted on Getro, such as Fast Forward's."""

import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from job_radar.model import Location, Period, Posting, RawPage, Salary, Search, Window, WorkMode


class GetroSource:
    """Pages through a Getro board's job search, newest jobs first.

    The search has no date filter, so paging stops at the first page that
    reaches back past the window's start; the filter step drops the older jobs
    on that page. Waits between requests, as the board's robots.txt asks, and
    retries timeouts, server errors and rate limits a few times before failing.
    A board that fails part way fails as a whole, so a fetch is never partial.
    Stateless: holds only the board, its HTTP client and its pacing.
    """

    name = "getro"
    SEARCH = "https://api.getro.com/api/v2/collections/{network}/search/jobs"
    PAGE_SIZE = 200  # the most the search returns per page
    RETRIES = 3
    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        network: str,
        http: httpx.Client,
        delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep the board's network id, the client, the pause between requests, and how to pause."""
        self._network = network
        self._http = http
        self._delay = delay
        self._sleep = sleep

    def fetch(self, search: Search, window: Window) -> list[RawPage]:
        """Fetch pages, newest jobs first, until one reaches back past the window's start.

        The search's criteria aren't sent: the whole window is small enough to
        fetch, and the filter step applies the criteria to every board alike.
        """
        pages: list[RawPage] = []
        while True:
            if pages:
                self._sleep(self._delay)
            body = self._page(len(pages))
            pages.append(RawPage(source=self.name, page=len(pages) + 1, body=body))
            results = json.loads(body)["results"]
            jobs = results["jobs"]
            fetched = (len(pages) - 1) * self.PAGE_SIZE + len(jobs)
            if not jobs or fetched >= results["count"] or self._oldest(jobs) < window.start:
                return pages

    def _page(self, index: int) -> str:
        """One page of the search, numbered from 0, retrying failures that may pass."""
        query = {"hits_per_page": self.PAGE_SIZE, "page": index, "filters": "", "query": ""}
        for attempt in range(1, self.RETRIES + 1):
            try:
                response = self._post(query)
                if response.status_code not in self.RETRY_STATUSES:
                    break
            except httpx.TransportError:
                pass
            self._sleep(self._delay * 2**attempt)
        else:
            response = self._post(query)  # the last try: any error now fails the fetch
        response.raise_for_status()
        return response.text

    def _post(self, query: dict) -> httpx.Response:
        """Send one search request."""
        url = self.SEARCH.format(network=self._network)
        return self._http.post(url, json=query, headers={"Accept": "application/json"})

    def _oldest(self, jobs: list[dict]) -> date:
        """The day the oldest job on a page was listed."""
        return GetroParser.listed_on(min(job["created_at"] for job in jobs))


class GetroParser:
    """Turns pages of a Getro board's job search into postings. Stateless."""

    source = "getro"
    WORK_MODES = {"on_site": WorkMode.ONSITE, "hybrid": WorkMode.HYBRID, "remote": WorkMode.REMOTE}
    PERIODS = {"year": Period.YEAR, "month": Period.MONTH, "hour": Period.HOUR}

    def parse(self, page: RawPage) -> list[Posting]:
        """Convert one page of search results into postings."""
        return [self._posting(job) for job in json.loads(page.body)["results"]["jobs"]]

    @staticmethod
    def listed_on(created_at: int) -> date:
        """The day a job was listed on the board, from the search's timestamp (UTC)."""
        return datetime.fromtimestamp(created_at, UTC).date()

    def _posting(self, job: dict) -> Posting:
        """One search result as a posting. The description comes later, only for jobs kept."""
        # TODO(task 7): fill in the description, for the jobs that pass the filter.
        return Posting(
            source=self.source,
            source_id=str(job["id"]),
            title=job["title"].strip(),
            company=job["organization"]["name"],
            locations=tuple(Location(text=text) for text in job["locations"]),
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
