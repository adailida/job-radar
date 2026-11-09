"""How runs work: every setting, with its default."""

from pathlib import Path

from pydantic import Field

from job_radar.model import Model
from job_radar.yaml_file import YamlFile


class LlmSettings(Model):
    """How the language model is asked."""

    model: str = "haiku"
    timeout_seconds: float = Field(120.0, gt=0)  # to wait for one answer
    batch_size: int = Field(20, ge=1)  # jobs per prompt
    max_description_chars: int = Field(4000, ge=0)  # how much of each description it sees


class RecommendSettings(Model):
    """Which scored jobs are recommended."""

    top_n: int = Field(10, ge=1)
    min_score: int = Field(40, ge=0, le=100)  # a lower score is a poor fit: not recommended


class GetroSettings(Model):
    """A job board on Getro."""

    network: str = "997"  # Fast Forward


class SourcesSettings(Model):
    """The job boards to fetch from."""

    getro: GetroSettings = GetroSettings()


class Settings(Model):
    """Everything a run can be configured with. Every key has a default.

    The user's `settings.yaml` holds only what they change; missing keys,
    at any depth, keep their defaults.
    """

    output: Path = Path("output")  # run folders go under output/runs/, demo runs under output/demo/
    lookback_days: int = Field(
        14, ge=1
    )  # how far back a run may reach: a first run, or a long break
    llm: LlmSettings = LlmSettings()
    recommend: RecommendSettings = RecommendSettings()
    sources: SourcesSettings = SourcesSettings()


class SettingsFile:
    """Reads the user's settings file over the defaults. Stateless: holds only the file."""

    def __init__(self, path: Path) -> None:
        """Keep the path of the user's `settings.yaml`."""
        self._file = YamlFile(path)

    def load(self) -> Settings:
        """The settings: the defaults, with the user's file over them if there is one."""
        return self._file.load(Settings) if self._file.exists() else Settings()
