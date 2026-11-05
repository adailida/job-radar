"""Builds the app for one terminal command: the only place that knows concrete classes."""

from pathlib import Path

from job_radar.app import JobRadarApp
from job_radar.clock import Clock
from job_radar.model import Model, Search


class Settings(Model):
    """Everything a run can be configured with."""

    # TODO(task 4): settle the defaults.
    # TODO(task 10): load from a settings file.
    output: Path = Path("output")  # run folders go under output/runs/
    local: Path = Path("local")  # the user's CV and preferences
    board: str = ""  # TODO(task 5): Fast Forward's board name on Getro.
    search: Search = Search(name="default", roles=())
    window_days: int = 7
    model: str = "haiku"
    batch_size: int = 20
    top_n: int = 10


class AppFactory:
    """Builds the app and everything it uses for one command (Factory).

    Wires concrete classes together, so every other class depends only on
    interfaces. Stateless: holds only the settings and the clock.
    """

    def __init__(self, settings: Settings, clock: Clock) -> None:
        """Keep the settings and the clock the app is built from."""
        self._settings = settings
        self._clock = clock

    def create(self) -> JobRadarApp:
        """Build the app: a new run folder, the steps in order, and the pipeline."""
        # TODO(task 4): build the run folder, checkpoints, steps and pipeline.
        raise NotImplementedError
