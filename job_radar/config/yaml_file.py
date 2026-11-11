"""Reading the user's YAML files into checked models."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from job_radar.utils.errors import SetupError


class ConfigError(SetupError):
    """A user file can't be used: missing, not YAML, or a value that doesn't fit."""


class YamlFile:
    """Reads one YAML file into a model, and says exactly what's wrong when it can't.

    Errors name the file and the path of the key at fault, such as
    `config_local/settings.yaml: recommend.min_scor: unknown key`, then how to fix
    it when the reader says. Stateless: holds only the file's path and the fix.
    """

    def __init__(self, path: Path, fix: str = "") -> None:
        """Keep the path of the file to read, and what an error adds on how to fix it."""
        self._path = path
        self._fix = fix

    def exists(self) -> bool:
        """Whether the file is there."""
        return self._path.is_file()

    def load[M: BaseModel](self, kind: type[M]) -> M:
        """Parse the file and check it against the model. An empty file is an empty mapping."""
        return self.check(kind, self.data())

    def data(self) -> dict:
        """The file's keys and values, unchecked. An empty file is an empty mapping."""
        try:
            data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise self._error(f"not valid YAML: {error}") from None
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise self._error("expected keys and values at the top level")
        return data

    def check[M: BaseModel](self, kind: type[M], data: dict) -> M:
        """Check data read from this file (or merged with it) against the model."""
        try:
            return kind.model_validate(data)
        except ValidationError as error:
            raise self._error(self._describe(error)) from None

    def _error(self, problem: str) -> ConfigError:
        """The error for a problem in this file: the file, the problem, and how to fix it."""
        return ConfigError(f"{self._path}: {problem}" + (f". {self._fix}" if self._fix else ""))

    @staticmethod
    def _describe(error: ValidationError) -> str:
        """Each problem as `key.path: what's wrong`, joined with "; "."""
        problems = []
        for item in error.errors():
            where = ".".join(str(part) for part in item["loc"]) or "(top level)"
            match item["type"]:
                case "extra_forbidden":
                    what = "unknown key"
                case "missing":
                    what = "required"
                case "value_error":
                    what = str(item["ctx"]["error"])
                case _:
                    what = item["msg"][:1].lower() + item["msg"][1:]
            problems.append(f"{where}: {what}")
        return "; ".join(problems)
