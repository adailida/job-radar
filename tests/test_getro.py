import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from job_radar.html_text import HtmlText
from job_radar.model import (
    Location,
    Period,
    RawPage,
    Salary,
    Search,
    SearchCriteria,
    Window,
    WorkMode,
)
from job_radar.places import PlaceCodes
from job_radar.sources.getro import GetroDescriber, GetroParser, GetroSource
from job_radar.sources.http import BoardClient, BoardError

FIXTURES = Path(__file__).parent / "fixtures" / "getro"
FIXTURE = FIXTURES / "search_page.json"
SEARCH = SearchCriteria(searches=(Search(name="default", roles=()),))
URL = "https://api.getro.com/api/v2/collections/997/search/jobs"
JOB_URL = "https://api.getro.com/api/v1/jobs/{id}?collection_id=997"


def fixture_page() -> RawPage:
    return RawPage(source="getro", page=1, body=FIXTURE.read_text())


def test_parse_reads_every_job_on_the_page():
    postings = GetroParser(PlaceCodes()).parse(fixture_page())
    assert [p.source_id for p in postings] == [
        "99005045",
        "98960032",
        "98883130",
        "99009773",
        "98973638",
    ]


def test_parse_maps_a_full_record():
    first = GetroParser(PlaceCodes()).parse(fixture_page())[0]
    assert first.key == "getro:99005045"
    assert (first.title, first.company) == ("Digital Strategy Project Manager", "Plan C")
    assert first.locations == (Location(text="Remote"),)
    assert first.work_mode is WorkMode.REMOTE
    assert first.salary == Salary(
        min=Decimal("125000"), max=Decimal("140000"), currency="USD", period=Period.YEAR
    )
    assert first.url.startswith("https://")
    assert first.posted_at == date(2026, 11, 5)
    assert first.description == ""


def test_parse_handles_hourly_pay_other_currencies_and_no_pay():
    postings = GetroParser(PlaceCodes()).parse(fixture_page())
    assert (postings[1].salary.min, postings[1].salary.period) == (Decimal("28"), Period.HOUR)
    assert postings[2].salary.currency == "EUR"
    assert postings[3].salary is None and postings[4].salary is None


def test_parse_handles_no_location_and_several():
    postings = GetroParser(PlaceCodes()).parse(fixture_page())
    assert postings[3].locations == ()
    assert len(postings[4].locations) == 6


def test_parse_reads_place_codes():
    postings = GetroParser(PlaceCodes()).parse(fixture_page())
    assert [(p.country, p.region) for p in postings[0].locations] == [(None, None)]
    assert [(p.country, p.region) for p in postings[2].locations] == [("GB", None)]
    assert (postings[4].locations[-1].text, postings[4].locations[-1].region) == (
        "Seattle, WA, USA",
        "US-WA",
    )
    assert postings[4].work_mode is WorkMode.ONSITE


def test_parse_trims_titles():
    assert (
        GetroParser(PlaceCodes()).parse(fixture_page())[2].title
        == "Research Software Engineer [UK-2026-RSE-1"
    )


def job(job_id: int, listed: date) -> dict:
    """A minimal search record listed at noon UTC on that day."""
    created = int(datetime.combine(listed, time(12), UTC).timestamp())
    return {"id": job_id, "created_at": created}


def page(jobs: list[dict], count: int) -> dict:
    return {"results": {"jobs": jobs, "count": count}}


class Board:
    """A fake Getro search: answers with set pages, or fails a set number of times first."""

    def __init__(self, pages: list[dict], failures: list[int | Exception] | None = None):
        self._pages = pages
        self._failures = list(failures or [])
        self.asked: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL
        if self._failures:
            failure = self._failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return httpx.Response(failure)
        index = json.loads(request.content)["page"]
        self.asked.append(index)
        return httpx.Response(200, json=self._pages[index])


def source(board: Board, sleeps: list[float]) -> GetroSource:
    http = httpx.Client(transport=httpx.MockTransport(board))
    return GetroSource("997", BoardClient(http, delay=1.0, sleep=sleeps.append))


def window(start: date) -> Window:
    return Window(start=start, end=date(2026, 11, 5))


def test_fetch_stops_at_the_page_that_reaches_past_the_window():
    pages = [
        page([job(1, date(2026, 11, 5)), job(2, date(2026, 11, 3))], count=6),
        page([job(3, date(2026, 11, 2)), job(4, date(2026, 10, 30))], count=6),
        page([job(5, date(2026, 10, 20)), job(6, date(2026, 10, 19))], count=6),
    ]
    board, sleeps = Board(pages), []
    fetched = source(board, sleeps).fetch(SEARCH, window(date(2026, 11, 1)))
    assert board.asked == [0, 1]
    assert [p.page for p in fetched] == [1, 2]
    assert sleeps == [1.0]


def test_fetch_stops_when_every_job_is_fetched():
    pages = [page([job(1, date(2026, 11, 5))], count=1)]
    board = Board(pages)
    source(board, []).fetch(SEARCH, window(date(2026, 1, 1)))
    assert board.asked == [0]


def test_fetch_stops_at_an_empty_page():
    board = Board([page([], count=0)])
    assert len(source(board, []).fetch(SEARCH, window(date(2026, 1, 1)))) == 1


def test_fetch_retries_server_errors_and_timeouts_with_backoff():
    timeout = httpx.ConnectTimeout("slow")
    board, sleeps = Board([page([job(1, date(2026, 11, 5))], count=1)], [503, timeout, 429]), []
    fetched = source(board, sleeps).fetch(SEARCH, window(date(2026, 1, 1)))
    assert len(fetched) == 1
    assert sleeps == [2.0, 4.0, 8.0]


def test_fetch_fails_after_the_last_retry():
    board = Board([page([], count=0)], [503, 503, 503, 503])
    with pytest.raises(BoardError, match="^HTTP 503 after 3 retries$"):
        source(board, []).fetch(SEARCH, window(date(2026, 1, 1)))


def test_a_board_that_never_answers_fails_in_a_few_words():
    def down(request):
        raise httpx.ConnectTimeout("slow")

    client = BoardClient(httpx.Client(transport=httpx.MockTransport(down)), 1.0, lambda s: None)
    with pytest.raises(BoardError, match="^no answer in time after 3 retries$"):
        client.get("https://example.org")

    def refused(request):
        raise httpx.ConnectError("refused")

    client = BoardClient(httpx.Client(transport=httpx.MockTransport(refused)), 1.0, lambda s: None)
    with pytest.raises(BoardError, match=r"^can't connect after 3 retries \(ConnectError\)$"):
        client.get("https://example.org")


def test_fetch_fails_at_once_on_a_client_error():
    board, sleeps = Board([page([], count=0)], [404]), []
    with pytest.raises(BoardError, match="^HTTP 404$"):
        source(board, sleeps).fetch(SEARCH, window(date(2026, 1, 1)))
    assert sleeps == []


def test_fetch_fails_as_a_whole_when_a_later_page_fails():
    class SecondPageDown(Board):
        def __call__(self, request):
            if json.loads(request.content)["page"] == 1:
                return httpx.Response(500)
            return super().__call__(request)

    pages = [page([job(1, date(2026, 11, 5))], count=2)]
    with pytest.raises(BoardError, match="HTTP 500 after 3 retries"):
        source(SecondPageDown(pages), []).fetch(SEARCH, window(date(2026, 1, 1)))


class JobPages:
    """A fake Getro job endpoint: set answers by id, after a set number of failures."""

    def __init__(self, answers: dict[str, httpx.Response], failures: list[int] | None = None):
        self._answers = answers
        self._failures = list(failures or [])
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        job_id = request.url.path.rsplit("/", 1)[-1]
        assert str(request.url) == JOB_URL.format(id=job_id)
        assert request.headers["Accept"] == "application/json"
        if self._failures:
            return httpx.Response(self._failures.pop(0))
        self.asked.append(job_id)
        return self._answers.get(job_id, httpx.Response(404, json={"error": "Job not found"}))


def detail(name: str, **changes) -> httpx.Response:
    """A recorded job response, with any fields changed."""
    body = json.loads((FIXTURES / name).read_text(encoding="utf-8")) | changes
    return httpx.Response(200, json=body)


def describer(pages: JobPages, sleeps: list[float]) -> GetroDescriber:
    http = httpx.Client(transport=httpx.MockTransport(pages))
    return GetroDescriber("997", BoardClient(http, delay=1.0, sleep=sleeps.append), HtmlText())


def search_posting(index: int = 0):
    return GetroParser(PlaceCodes()).parse(fixture_page())[index]


def test_describe_gives_the_description_as_plain_text():
    pages = JobPages({"99005045": detail("job_detail.json")})
    text = describer(pages, []).describe(search_posting(0))
    assert text.startswith("Department: Digital\nReports to: Executive Director\n")
    assert "\n\nJob Summary\n\n" in text
    assert "\n- Oversee organic search visibility, including SEO and AEO" in text
    assert "<" not in text


def test_describe_pauses_before_every_request():
    pages, sleeps = JobPages({"99005045": detail("job_detail.json")}), []
    getro = describer(pages, sleeps)
    getro.describe(search_posting(0))
    getro.describe(search_posting(0))
    assert sleeps == [1.0, 1.0]
    assert getro.pace == 1.0


def test_describe_gives_nothing_when_the_board_has_no_description():
    pages = JobPages({"98883130": detail("job_no_description.json")})
    assert describer(pages, []).describe(search_posting(2)) == ""


def test_describe_gives_nothing_for_a_job_the_board_no_longer_has():
    assert describer(JobPages({}), []).describe(search_posting(0)) == ""


def test_describe_gives_nothing_for_a_job_no_longer_active():
    pages = JobPages({"99005045": detail("job_detail.json", status="closed")})
    assert describer(pages, []).describe(search_posting(0)) == ""


def test_describe_retries_server_errors_with_backoff():
    pages, sleeps = JobPages({"99005045": detail("job_detail.json")}, [503, 429]), []
    assert describer(pages, sleeps).describe(search_posting(0))
    assert sleeps == [1.0, 2.0, 4.0]  # the pause, then two backoffs


def test_describe_fails_after_the_last_retry():
    pages = JobPages({}, [500, 500, 500, 500])
    with pytest.raises(BoardError, match="HTTP 500 after 3 retries"):
        describer(pages, []).describe(search_posting(0))


def test_describe_fails_at_once_on_other_client_errors():
    pages, sleeps = JobPages({}, [403]), []
    with pytest.raises(BoardError, match="^HTTP 403$"):
        describer(pages, sleeps).describe(search_posting(0))
    assert sleeps == [1.0]  # the pause only


@pytest.mark.live
@pytest.mark.enable_socket
def test_live_fast_forward_search_still_parses():
    """Opt-in: `uv run pytest -m live`. One request to the real board."""
    http = httpx.Client(headers={"User-Agent": "job-radar tests"}, timeout=20)
    today = date.today()
    pages = GetroSource("997", BoardClient(http)).fetch(SEARCH, Window(start=today, end=today))
    postings = GetroParser(PlaceCodes()).parse(pages[0])
    assert postings, "the board returned no jobs"
    assert all(p.title and p.company and p.url for p in postings)


@pytest.mark.live
@pytest.mark.enable_socket
def test_live_fast_forward_job_still_describes():
    """Opt-in: `uv run pytest -m live`. Two requests to the real board: one search, one job."""
    http = httpx.Client(headers={"User-Agent": "job-radar tests"}, timeout=20)
    client = BoardClient(http)
    today = date.today()
    pages = GetroSource("997", client).fetch(SEARCH, Window(start=today, end=today))
    postings = GetroParser(PlaceCodes()).parse(pages[0])
    text = GetroDescriber("997", client, HtmlText()).describe(postings[0])
    assert "<p>" not in text


def test_a_board_is_named_for_people_by_its_network():
    client = BoardClient(httpx.Client())
    assert GetroSource("997", client).label == "Fast Forward"
    assert GetroSource("123", client).label == "Getro board 123"
