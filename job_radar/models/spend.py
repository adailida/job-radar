"""What a paid source is expected to cost, what was agreed, and what it spent."""

from datetime import date
from enum import StrEnum

from job_radar.models.model import Model
from job_radar.models.posting import RawPage


class DayCount(Model):
    """How many jobs a paid source's free count found for one search on one day."""

    search: str  # the search's name in the profile
    day: date
    found: int


class SpendPlan(Model):
    """What a paid source expects a run to cost, and the limits to check it against."""

    source: str
    estimate: int  # the most the run's searches can cost: their match counts added up
    estimated: bool  # False when the source couldn't count, and the estimate is ask_above
    credits_left: int
    ask_above: int  # a run that needs more credits asks first
    budget_left: int  # what the monthly budget still allows; the credits left on a one-time grant
    counts: tuple[DayCount, ...] = ()  # each search and day it could count, for sources that do


class SpendDecision(StrEnum):
    """How a paid source's spend was agreed."""

    AUTO = "auto"  # within every limit
    APPROVED = "approved"  # over a limit, and the user said go ahead
    SKIPPED = "skipped"  # the user chose to leave the source out of this run
    FAILED = "failed"  # the source failed at the cost check, so it is left out of this run


class Approval(Model):
    """The spend agreed for one paid source before anything is fetched."""

    source: str
    estimate: int
    estimated: bool = True  # False when the source couldn't count, and the estimate is ask_above
    decision: SpendDecision
    cap: int  # the most the fetch may spend: the estimate plus 10%, within the credits left
    credits_before: int  # 0 when the cost check failed
    budget_left: int | None = None  # what the monthly budget still allowed; None in older runs
    failure: str | None = None  # why the cost check failed, when it did
    counts: tuple[DayCount, ...] = ()  # the plan's count per search and day, for the fetch


class PaidFetch(Model):
    """What a paid source fetched and what it cost."""

    pages: tuple[RawPage, ...]
    charged: int
    credits_left: int
    extra_approved: int = 0  # credits the user agreed to during the fetch, past the approval's cap


class Spend(Model):
    """One paid source's spend in a run: what was agreed and what it cost."""

    approval: Approval
    charged: int = 0
    credits_after: int | None = None  # None when the source was skipped
    extra_approved: int = 0  # credits the user agreed to during the fetch, past the approval's cap
