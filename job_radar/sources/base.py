"""The interfaces a job board brings: one to fetch, one to parse, and one to describe."""

from typing import Protocol, runtime_checkable

from job_radar.model import PaidFetch, Posting, RawPage, SearchCriteria, SpendPlan, Window


@runtime_checkable
class JobBoardSource(Protocol):
    """Talks to one job board's API (Adapter).

    Stateless: holds only its configuration and HTTP client.
    """

    name: str  # "getro", "jobspipe"; also the name of its parser's source

    def fetch(self, criteria: SearchCriteria, window: Window) -> list[RawPage]:
        """Query the board for the searches and window, page by page, unparsed."""
        ...


@runtime_checkable
class PaidSource(JobBoardSource, Protocol):
    """A board that charges for what it returns: it can say what a run will cost (Adapter)."""

    def plan(self, criteria: SearchCriteria, window: Window) -> SpendPlan:
        """What the searches would cost and the limits that apply, without spending anything."""
        ...

    def fetch_paid(self, criteria: SearchCriteria, window: Window, cap: int) -> PaidFetch:
        """Fetch, spending at most `cap` credits, and say what it cost."""
        ...


@runtime_checkable
class JobBoardParser(Protocol):
    """Turns one job board's records into postings (Adapter). Stateless."""

    source: str  # the board whose pages it parses

    def parse(self, page: RawPage) -> list[Posting]:
        """Convert one raw page into postings."""
        ...


@runtime_checkable
class JobDescriber(Protocol):
    """Fetches the full description of one posting, for boards whose search leaves it out.

    Adapter. Stateless: holds only its configuration and client.
    """

    source: str  # the board whose postings it describes
    pace: float  # seconds each description takes at least, for telling the user how long

    def describe(self, posting: Posting) -> str:
        """The posting's description as plain text; empty when the board has none."""
        ...
