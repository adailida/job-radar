"""How runs work: every setting, read from the defaults file with the user's changes over it."""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from job_radar.model import Model
from job_radar.yaml_file import YamlFile


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


class ReportSettings(Model):
    """How the report is laid out."""

    group_by: Literal["job_type", "domain", "both"]  # the headings in "New openings"
    requirements_per_type: int = Field(ge=1)  # rows per type in "What employers ask for"
    gap_suggestions: int = Field(ge=0)  # gaps shown with how to gain them in "Experience to gain"


class RecommendSettings(Model):
    """Which scored jobs are recommended."""

    top_n: int = Field(ge=1)
    min_score: int = Field(ge=0, le=100)  # a lower score is a poor fit: not recommended


class GetroSettings(Model):
    """A job board on Getro."""

    network: str  # the Getro board: 997 is Fast Forward


class JobsPipeSettings(Model):
    """JobsPipe, a paid job API: off until turned on, and capped per run."""

    enabled: bool
    api_key_env: str  # the variable in the environment or .env
    plan: Literal["free", "seeker"]  # sets the per-run max and the monthly budget
    max_jobs_per_run: int | None = Field(ge=1)  # per-run max; None takes the plan's
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

    The values come from `default_settings.yaml`, with the user's
    `settings.yaml` merged over it; the model has no defaults of its own, so
    that file is the one place they live.
    """

    output: Path  # run folders go under output/runs/, demo runs under output/demo/
    # how far back a run may reach: a first run, or after a long break
    lookback_days: int = Field(ge=1)
    new_only: bool  # drop jobs an earlier run already found
    trend_period: Literal["week", "month", "quarter"]  # what market trends compare
    llm: LlmSettings
    job_types: dict[str, str] = Field(min_length=1)  # name: what the LLM is told it means
    domains: dict[str, str] = Field(min_length=1)  # name: what the LLM is told it means
    recommend: RecommendSettings
    report: ReportSettings
    sources: SourcesSettings


class SettingsFile:
    """Reads the default settings, then the user's settings file over them.

    The user's file holds only what they change; it is merged over the
    defaults at any depth (a nested key replaces only itself; lists and values
    replace whole). Stateless: holds only the two files.
    """

    DEFAULTS = Path(__file__).with_name("default_settings.yaml")

    def __init__(self, path: Path, defaults: Path = DEFAULTS) -> None:
        """Keep the path of the user's `settings.yaml`, and of the defaults."""
        self._file = YamlFile(path)
        self._defaults = YamlFile(defaults)

    def load(self) -> Settings:
        """The settings: the defaults, with the user's file over them if there is one."""
        changes = self._file.data() if self._file.exists() else {}
        return self._file.check(Settings, self._merge(self._defaults.data(), changes))

    @classmethod
    def defaults(cls, **changes: Any) -> Settings:
        """The default settings with these changes merged over them, for code and tests."""
        merged = cls._merge(YamlFile(cls.DEFAULTS).data(), changes)
        return YamlFile(cls.DEFAULTS).check(Settings, merged)

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
