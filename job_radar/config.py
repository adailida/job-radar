"""Builds the App. Settings and defaults arrive in task 7; stages and alerts in task 4."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from job_radar.llm.base import LLM
from job_radar.sources.base import Source
from job_radar.store.base import RunStore
from job_radar.ui.base import Prompter


def local_now() -> datetime:
    """Current local time with its UTC offset, so run ids match the user's clock."""
    return datetime.now().astimezone()


@dataclass
class App:
    """The configured objects a run uses. Tests pass fakes and a fixed `now`."""

    llm: LLM
    store: RunStore
    prompter: Prompter
    sources: list[Source] = field(default_factory=list)
    now: Callable[[], datetime] = local_now
