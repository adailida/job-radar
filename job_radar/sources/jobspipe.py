"""JobsPipe: a paid job API that aggregates LinkedIn, Indeed and employers' own ATS."""

import json
import re
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pycountry

from job_radar.matching.place_codes import PlaceCodes
from job_radar.models import (
    DayCount,
    IfMissing,
    Location,
    PaidFetch,
    Period,
    Posting,
    RawPage,
    Salary,
    Search,
    SearchCriteria,
    SpendPlan,
    Window,
    WorkMode,
)
from job_radar.sources.board_client import BoardClient
from job_radar.utils.errors import JobRadarError
from job_radar.utils.html_text import HtmlText
from job_radar.utils.progress import NoProgress, Progress
from job_radar.utils.prompter import Prompter


class JobsPipeError(JobRadarError):
    """JobsPipe refused a request, so its jobs can't be part of this run."""


class JobsPipeSource:
    """Searches JobsPipe per search and day, newest first, asking before it spends more than agreed.

    Each search's criteria are sent so JobsPipe filters on its side, with the
    source-only filters from the settings added as written. Each day of the
    window is its own query, as phrase searches over longer spans time out.
    One credit buys one job for the calendar month; jobs already paid for are
    free. Before a run it says what the searches would cost, for free: the
    account's credits and the matches counted for each search and day. The
    plan sets the limit a run asks above and the monthly budget unless the
    settings override them. Says which search and day it is on as it goes.
    Stateless: holds only its client, filters, limits and who it asks and tells.
    """

    name = "jobspipe"
    label = "JobsPipe"
    SEARCH = "https://api.jobspipe.dev/v1/jobs/search"
    ACCOUNT = "https://api.jobspipe.dev/v1/account"
    ESTIMATE = "https://api.jobspipe.dev/v1/jobs/export/estimate"
    PAGE_SIZE = 25  # the most a page holds on the Free plan
    PLANS = {"free": (250, None), "seeker": (2500, 10_000)}  # ask above, monthly budget

    def __init__(
        self,
        client: BoardClient,
        filters: dict,
        limits: tuple[int, int | None],
        prompter: Prompter,
        match_if_missing: bool = True,
        progress: Progress | None = None,
    ) -> None:
        """Keep the client (which carries the key), the extra filters, the limits, who to tell.

        `limits` is the credits a run asks above and the monthly budget (None for a one-time
        grant, where the budget is what's left). With `match_if_missing` off,
        jobs that don't say are never asked for.
        """
        self._client = client
        self._filters = filters
        self._ask_above, self._budget = limits
        self._prompter = prompter
        self._match_if_missing = match_if_missing
        self._progress = progress or NoProgress()

    def plan(self, criteria: SearchCriteria, window: Window) -> SpendPlan:
        """What the searches would cost this run, and the limits, without spending a credit.

        Each search is counted for each day and the counts added up. When
        JobsPipe can't count one (a slow phrase search can time out), the
        estimate is the ask-above limit, marked as not counted. The plan keeps
        each count it got, for the fetch.
        """
        account = self._account()
        left = account["credits_remaining"]
        counts: list[DayCount] = []
        counted = True
        for search, day in self._queries(criteria, window):
            self._client.pause()
            response = self._client.post(self.ESTIMATE, json=self.query(search, day))
            if response.status_code != 200:
                counted = False
                break
            found = response.json().get("rows") or 0
            counts.append(DayCount(search=search.name, day=day, found=found))
        estimate = sum(count.found for count in counts) if counted else self._ask_above
        used = account.get("credits_used") or 0
        budget_left = left if self._budget is None else max(self._budget - used, 0)
        return SpendPlan(
            source=self.name,
            estimate=estimate,
            estimated=counted,
            credits_left=left,
            ask_above=self._ask_above,
            budget_left=budget_left,
            counts=tuple(counts),
        )

    def fetch(self, criteria: SearchCriteria, window: Window) -> list[RawPage]:
        """Pages of every search, when no cost check ran; above the limit, it asks to go on."""
        return list(self.fetch_paid(criteria, window, self._ask_above).pages)

    def fetch_paid(
        self, criteria: SearchCriteria, window: Window, cap: int, counts: tuple[DayCount, ...] = ()
    ) -> PaidFetch:
        """Pages of every search and day until each runs out, asking before spending over `cap`.

        When `cap` credits are spent with jobs still to fetch, the user is
        asked whether to keep going for up to `cap` more, within the credits
        left, and again each time that runs out. A fetch is never partial: if
        the user says no, the credits run out, or a day its plan's `counts`
        found jobs for comes back empty, it raises `JobsPipeError` instead of
        giving part of the results.
        """
        found = {(count.search, count.day): count.found for count in counts}
        pages: list[RawPage] = []
        budget, charged, left, approved = cap, 0, 0, cap
        so_far = 0
        queries = self._queries(criteria, window) if cap > 0 else ()  # none agreed, none sent
        days = (window.end - window.start).days + 1
        for number, (search, day) in enumerate(queries):
            cursor: str | None = None
            while True:
                if budget <= 0:
                    budget = self._more(pages, charged, left, cap, approved)
                    approved += budget
                self._progress.detail(
                    f"{self.label} {search.name}, {day:%b} {day.day} "
                    f"(day {number % days + 1} of {days}), {so_far} jobs so far"
                )
                if pages:
                    self._client.pause()
                body = self.query(search, day) | {"limit": min(self.PAGE_SIZE, budget)}
                page = self._search(body | ({"cursor": cursor} if cursor else {}))
                pages.append(RawPage(source=self.name, page=len(pages) + 1, body=json.dumps(page)))
                metadata, jobs = page.get("metadata", {}), page.get("data", [])
                budget -= len(jobs)
                so_far += len(jobs)
                charged += metadata.get("credits_charged") or 0
                left = metadata.get("credits_remaining", left)
                if not jobs and cursor is None and found.get((search.name, day), 0) > 0:
                    self._told(pages, charged, left)
                    raise self._timed_out(search, day, found[search.name, day], charged)
                cursor = metadata.get("next_cursor")
                if not jobs or not cursor:
                    break
        if not pages:
            left = self._account()["credits_remaining"]
        self._told(pages, charged, left)
        return PaidFetch(
            pages=tuple(pages), charged=charged, credits_left=left, extra_approved=approved - cap
        )

    def _more(self, pages: list[RawPage], charged: int, left: int, cap: int, approved: int) -> int:
        """How many more credits the user agrees to, `cap` at most, when the approved ones ran out.

        Raises `JobsPipeError` when the user says no or no credits are left,
        as a fetch is all or nothing.
        """
        found = self._found(pages)
        more = min(cap, left)
        reason = "the credits left allow"
        if more > 0:
            if self._prompter.confirm(
                f"{self.label}: {found} jobs fetched ({charged} credits) and more to go. "
                f"Keep going for up to {more} more?",
                default=False,
            ):
                return more
            reason = f"the {approved} approved"
        self._told(pages, charged, left)
        raise JobsPipeError(
            f"found more jobs than {reason}, so none are used, as a fetch is "
            f"all or nothing ({charged} credits used; jobs paid for are free again this month)"
        )

    @staticmethod
    def _timed_out(search: Search, day: date, found: int, charged: int) -> JobsPipeError:
        """The error for a day that came back empty though its count found jobs.

        JobsPipe answers a search that timed out with no jobs and no error, so
        the count is what tells it apart from a day with none.
        """
        return JobsPipeError(
            f"the search for {search.name} on {day.day} {day:%b} came back empty though its "
            f"count found {found}, so it probably timed out; none of the jobs are used, and "
            f"the next run fetches these dates again ({charged} credits used; jobs paid for "
            "are free again this month)"
        )

    def _told(self, pages: list[RawPage], charged: int, left: int) -> None:
        """Tell the user what the fetch found and spent."""
        self._prompter.tell(
            f"{self.label}: {self._found(pages)} jobs, {charged} credits used, {left} left."
        )

    @staticmethod
    def _found(pages: list[RawPage]) -> int:
        """How many jobs the pages hold."""
        return sum(len(json.loads(page.body)["data"]) for page in pages)

    @staticmethod
    def _queries(criteria: SearchCriteria, window: Window) -> Iterator[tuple[Search, date]]:
        """Each search with each day of the window, newest day first."""
        days = (window.end - window.start).days + 1
        for search in criteria.searches:
            for back in range(days):
                yield search, window.end - timedelta(days=back)

    def query(self, search: Search, day: date) -> dict:
        """The search body for one search on one day, with the extra filters added.

        A criterion that keeps jobs which don't say also asks JobsPipe to
        return jobs whose value is unknown, so both sides agree, unless that is
        turned off to spend less.
        """
        body: dict = {"posted_at_gte": day.isoformat(), "posted_at_lte": day.isoformat()}
        unknown: list[str] = []
        if search.roles:
            body["job_title_or"] = list(search.roles)
        if search.exclude_titles:
            body["job_title_not"] = list(search.exclude_titles)
        if search.work_mode:
            body["work_arrangement_or"] = [mode.value for mode in search.work_mode.values]
            if search.work_mode.if_missing is IfMissing.KEEP:
                unknown.append("work_arrangement")
        if search.locations:
            countries = [code for code in search.locations.values if "-" not in code]
            regions = [code for code in search.locations.values if "-" in code]
            if countries:
                body["job_country_code_or"] = countries
            if regions:
                body["region_or"] = regions
            if search.locations.if_missing is IfMissing.KEEP:
                unknown.append("location")
        salary = search.min_salary
        if salary and salary.currency == "USD":
            yearly = {Period.YEAR: 1, Period.MONTH: 12, Period.HOUR: 2080}[salary.period]
            body["min_salary_usd"] = int(salary.amount * yearly)
            if salary.if_missing is IfMissing.KEEP:
                unknown.append("salary")
        extra = dict(self._filters)
        if not self._match_if_missing:
            unknown = []
        unknown += [field for field in extra.pop("include_unknown", []) if field not in unknown]
        return body | extra | ({"include_unknown": unknown} if unknown else {})

    def _account(self) -> dict:
        """The account's plan and credits; costs nothing."""
        return self._json(self._client.get(self.ACCOUNT))

    def _search(self, body: dict) -> dict:
        """One page of a search."""
        return self._json(self._client.post(self.SEARCH, json=body))

    def _json(self, response) -> dict:
        """The response's JSON, or an error that says the status and what JobsPipe said."""
        if response.status_code != 200:
            try:
                said = response.json().get("message") or response.json().get("error")
            except ValueError:
                said = response.text[:200]
            status = self._client.status(response.status_code)
            raise JobsPipeError(f"{status}: {said}" if said else status)
        return response.json()


class JobsPipeParser:
    """Turns pages of JobsPipe search results into postings.

    JobsPipe sends full descriptions, country codes, states and yearly pay, so
    these postings need no describer. Places not coded by JobsPipe are read
    like any board's. Stateless: holds only how places and HTML are read.
    """

    source = "jobspipe"
    WORK_MODES = {"remote": WorkMode.REMOTE, "hybrid": WorkMode.HYBRID, "onsite": WorkMode.ONSITE}
    TAG = re.compile(r"<(p|br|li|ul|ol|div|h[1-6])\b", re.IGNORECASE)

    def __init__(self, places: PlaceCodes, html: HtmlText) -> None:
        """Keep how places are read into codes, and how HTML becomes text."""
        self._places = places
        self._html = html

    def parse(self, page: RawPage) -> list[Posting]:
        """Convert one page of search results into postings."""
        return [self._posting(job) for job in json.loads(page.body).get("data", [])]

    def _posting(self, job: dict) -> Posting:
        """One search result as a posting."""
        description = job.get("description") or ""
        return Posting(
            source=self.source,
            source_id=str(job["id"]),
            title=job["job_title"].strip(),
            company=job["company"],
            locations=self._locations(job),
            work_mode=self._work_mode(job),
            salary=self._salary(job),
            url=job.get("url") or job.get("source_url") or "",
            posted_at=date.fromisoformat(job["date_posted"][:10])
            if job.get("date_posted")
            else None,
            description=self._html.text(description)
            if self.TAG.search(description)
            else description,
        )

    def _locations(self, job: dict) -> tuple[Location, ...]:
        """The posting's place, with JobsPipe's country and state codes when it gives them."""
        text = job.get("location") or job.get("country")
        if not text:
            return ()
        located = self._places.locate(Location(text=text))
        country = job.get("country_code") or located.country
        region = self._region(country, job.get("state_code")) or located.region
        return (located.model_copy(update={"country": country, "region": region}),)

    @staticmethod
    def _region(country: str | None, state: str | None) -> str | None:
        """The ISO region code for a state JobsPipe gives as a code ("WA"), if it is one."""
        if not country or not state:
            return None
        code = f"{country}-{state}"
        return code if pycountry.subdivisions.get(code=code) else None

    def _work_mode(self, job: dict) -> WorkMode:
        """The work arrangement, or remote when only the remote flag is set; else unknown."""
        if job.get("work_arrangement") in self.WORK_MODES:
            return self.WORK_MODES[job["work_arrangement"]]
        return WorkMode.REMOTE if job.get("remote") else WorkMode.UNKNOWN

    @staticmethod
    def _salary(job: dict) -> Salary | None:
        """The yearly pay range in its own currency, when JobsPipe gives one."""
        low, high, currency = (
            job.get("min_annual_salary"),
            job.get("max_annual_salary"),
            job.get("salary_currency"),
        )
        if currency is None or (low is None and high is None):
            return None
        return Salary(
            min=None if low is None else Decimal(low),
            max=None if high is None else Decimal(high),
            currency=currency,
            period=Period.YEAR,
            text=job.get("salary_string"),
        )
