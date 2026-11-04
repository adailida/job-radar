"""Builds the App: the set of configured objects a run works with."""

# TODO(task 7): load settings with defaults and build the App from them.

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from job_radar.llm.base import LLM
from job_radar.sources.base import Source
from job_radar.store.base import RunStore
from job_radar.ui.base import Prompter


def local_now() -> datetime:
    """Current local time with its UTC offset, so run ids and dates match the user's clock."""
    return datetime.now().astimezone()


@dataclass
class App:
    """Everything a run works with: the language model, run storage, user prompts,
    job sources and the clock.

    Tests build one with fakes and a fixed clock, so runs are repeatable.

    Holds configured objects only, never data from a run, so one App can serve
    several runs.
    """

    # TODO(task 4): add the stages and the alerts collector.
    llm: LLM
    store: RunStore
    prompter: Prompter
    sources: list[Source] = field(default_factory=list)
    now: Callable[[], datetime] = local_now
