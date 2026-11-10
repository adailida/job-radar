"""Talking to a job board over HTTP at the pace it asks for."""

import time
from collections.abc import Callable

import httpx

from job_radar.errors import JobRadarError


class BoardError(JobRadarError):
    """A request to a job board failed for good, in a few words: "HTTP 503 after 3 retries"."""


class BoardClient:
    """Sends requests to one job board politely: paced, and retried when a failure may pass.

    Retries timeouts, server errors and rate limits a few times, waiting longer
    each time. The last try's response comes back whatever its status, so the
    caller decides what an error means; `check` turns an error status into a
    `BoardError`. When the last try gets no answer at all, that is a
    `BoardError` too. Callers pause between requests, as the board's
    robots.txt asks. Stateless: holds only the HTTP client, the pause and how
    to pause.
    """

    RETRIES = 3
    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        http: httpx.Client,
        delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep the client, the pause between requests in seconds, and how to pause."""
        self._http = http
        self._delay = delay
        self._sleep = sleep

    @property
    def delay(self) -> float:
        """The pause between requests, in seconds."""
        return self._delay

    def pause(self) -> None:
        """Wait the board's delay before the next request."""
        self._sleep(self._delay)

    def get(self, url: str, **kwargs) -> httpx.Response:
        """Send a GET, retrying failures that may pass."""
        return self._send(lambda: self._http.get(url, **kwargs))

    def post(self, url: str, **kwargs) -> httpx.Response:
        """Send a POST, retrying failures that may pass."""
        return self._send(lambda: self._http.post(url, **kwargs))

    def _send(self, request: Callable[[], httpx.Response]) -> httpx.Response:
        """Send the request until it gets an answer worth keeping, or the tries run out."""
        for attempt in range(1, self.RETRIES + 1):
            try:
                response = request()
                if response.status_code not in self.RETRY_STATUSES:
                    return response
            except httpx.TransportError:
                pass
            self._sleep(self._delay * 2**attempt)
        try:
            return request()  # the last try
        except httpx.TimeoutException:
            raise BoardError(f"no answer in time after {self.RETRIES} retries") from None
        except httpx.TransportError as error:
            raise BoardError(
                f"can't connect after {self.RETRIES} retries ({type(error).__name__})"
            ) from None

    def check(self, response: httpx.Response) -> httpx.Response:
        """The response when it succeeded; a `BoardError` naming its status when not."""
        if response.is_success:
            return response
        raise BoardError(self.status(response.status_code))

    def status(self, code: int) -> str:
        """An error status in words, with any retries: "HTTP 503 after 3 retries"."""
        retried = code in self.RETRY_STATUSES
        return f"HTTP {code}" + (f" after {self.RETRIES} retries" if retried else "")
