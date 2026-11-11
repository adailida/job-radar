"""How runs work: every setting, read from the defaults file with the user's changes over it."""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from job_radar.config.yaml_file import ConfigError, YamlFile
from job_radar.models import Model


class LlmSettings(Model):
    """How the language model is asked."""

    model: str  # the Claude model that scores jobs
    timeout_seconds: float = Field(gt=0)  # to wait for one answer
    batch_size: int = Field(ge=1)  # jobs per prompt
    max_description_chars: int = Field(ge=0)  # how much of each description it sees
    classify_batch_size: int = Field(ge=1)  # jobs per prompt when labelling
    classify_description_chars: int = Field(ge=0)  # labelling reads only the start
    extract_batch_size: int = Field(ge=1)  # jobs per prompt when finding requirements
    extract_description_chars: int = Field(ge=0)  # how much of each description that reads
    ask_above_jobs: int = Field(ge=1)  # a run with more jobs for the LLM asks first; none cut


class ReportSettings(Model):
    """How the report is laid out."""

    group_by: Literal["job_type", "domain", "both"]  # the headings in "New openings"
    requirements_per_type: int = Field(ge=1)  # rows per type in "What employers ask for"
    gap_suggestions: int = Field(ge=0)  # gaps shown with how to gain them in "Experience to gain"


class AlertSettings(Model):
    """When a run warns about something that didn't stop it."""

    low_credits: int = Field(ge=0)  # warn when a paid source has fewer credits left after a run


class RecommendSettings(Model):
    """Which scored jobs are recommended."""

    top_n: int = Field(ge=1)
    min_score: int = Field(ge=0, le=100)  # a lower score is a poor fit: not recommended


class GetroSettings(Model):
    """A job board on Getro."""

    network: str  # the Getro board: 997 is Fast Forward


class JobsPipeSettings(Model):
    """JobsPipe, a paid job API: off until turned on; a run that needs more credits asks."""

    enabled: bool
    api_key_env: str  # the variable in the environment or config_local/.env
    plan: Literal["free", "seeker"]  # sets the ask-above limit and the monthly budget
    ask_above_credits: int | None = Field(ge=1)  # a run needing more asks first; None: the plan's
    monthly_budget: int | None = Field(ge=1)  # None takes the plan's
    delay_seconds: float = Field(ge=0)  # between requests
    # Also ask for jobs that don't say, where a criterion's if_missing keeps them.
    # Matches the local filter; false sends stricter queries, for fewer credits.
    match_if_missing: bool
    filters: dict[str, Any]  # JobsPipe-only search filters, sent as written


class SourcesSettings(Model):
    """The job boards to fetch from."""

    getro: GetroSettings
    jobspipe: JobsPipeSettings


class Settings(Model):
    """Everything a run can be configured with: the types and limits of each setting.

    The values come from `config/settings.yaml`, with the user's
    `config_local/settings.yaml` merged over it; the model has no defaults of
    its own, so that file is the one place they live.
    """

    output: Path  # run folders go under output/runs/, demo runs under output/demo/
    # how far back a run may reach: a first run, or after a long break
    lookback_days: int = Field(ge=1)
    new_only: bool  # drop jobs an earlier run already found
    verbose: bool  # show the start banner and a line per step; `--quiet` turns it off too
    trend_period: Literal["week", "month", "quarter"]  # what market trends compare
    llm: LlmSettings
    job_types: dict[str, str] = Field(min_length=1)  # name: what the LLM is told it means
    domains: dict[str, str] = Field(min_length=1)  # name: what the LLM is told it means
    recommend: RecommendSettings
    report: ReportSettings
    alerts: AlertSettings
    sources: SourcesSettings


class SettingsFile:
    """Reads the default settings, then the user's settings file over them.

    The user's file holds only what they change; it is merged over the
    defaults at any depth (a nested key replaces only itself; lists and values
    replace whole). Stateless: holds only the two files.
    """

    DEFAULTS = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
    DEFAULTS_NAME = "config/settings.yaml"  # where to find the defaults, for people

    def __init__(self, path: Path, defaults: Path = DEFAULTS) -> None:
        """Keep the path of the user's `settings.yaml`, and of the defaults."""
        self._file = YamlFile(
            path, fix=f"Fix it in {path}; {self.DEFAULTS_NAME} lists every setting with its default"
        )
        self._defaults = defaults

    def load(self) -> Settings:
        """The settings: the defaults, with the user's file over them if there is one."""
        changes = self._file.data() if self._file.exists() else {}
        return self._file.check(Settings, self._merge(self._read(self._defaults), changes))

    @classmethod
    def defaults(cls, **changes: Any) -> Settings:
        """The default settings with these changes merged over them, for code and tests."""
        merged = cls._merge(cls._read(cls.DEFAULTS), changes)
        return YamlFile(cls.DEFAULTS).check(Settings, merged)

    @classmethod
    def _read(cls, defaults: Path) -> dict:
        """The default settings, unchecked; a setup error naming the file when it is missing."""
        if not defaults.is_file():
            raise ConfigError(
                f"{defaults}: the default settings are missing. They come with the code, "
                f"in {cls.DEFAULTS_NAME} at the repo root: restore it from the repo"
            )
        return YamlFile(defaults).data()

    @classmethod
    def _merge(cls, base: dict, changes: dict) -> dict:
        """The base with the changes over it: mappings merge key by key, anything else replaces."""
        merged = dict(base)
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = cls._merge(merged[key], value)
            else:
                merged[key] = value
        return merged
