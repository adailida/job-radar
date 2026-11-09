from pathlib import Path

import pytest

from job_radar.cli import Cli
from job_radar.settings import RecommendSettings, Settings, SettingsFile
from job_radar.yaml_file import ConfigError

EXAMPLE = Path(__file__).parent.parent / "examples" / "settings.example.yaml"


def load(tmp_path, text: str) -> Settings:
    """The settings from a file with this text."""
    path = tmp_path / "settings.yaml"
    path.write_text(text)
    return SettingsFile(path).load()


def test_no_file_means_every_default(tmp_path):
    assert SettingsFile(tmp_path / "settings.yaml").load() == Settings()


def test_an_empty_file_means_every_default(tmp_path):
    assert load(tmp_path, "# nothing changed\n") == Settings()


def test_the_file_changes_only_what_it_sets_at_any_depth(tmp_path):
    settings = load(tmp_path, "lookback_days: 3\nrecommend: {min_score: 0}\n")
    assert settings.lookback_days == 3
    assert settings.recommend == RecommendSettings(top_n=10, min_score=0)
    assert settings.llm == Settings().llm


def test_an_unknown_key_is_an_error_naming_its_path(tmp_path):
    with pytest.raises(ConfigError, match=r"settings.yaml: recommend.min_scor: unknown key"):
        load(tmp_path, "recommend: {min_scor: 0}\n")


def test_a_value_out_of_range_is_an_error_naming_its_path(tmp_path):
    with pytest.raises(ConfigError, match=r"recommend.min_score: input should be less than or"):
        load(tmp_path, "recommend: {min_score: 120}\n")


def test_every_problem_is_named(tmp_path):
    with pytest.raises(ConfigError, match=r"lookback_days: .*; llm.modle: unknown key"):
        load(tmp_path, "lookback_days: soon\nllm: {modle: opus}\n")


def test_a_file_that_isnt_yaml_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match=r"settings.yaml: not valid YAML"):
        load(tmp_path, "recommend: {min_score: 0\n")


def test_a_file_without_keys_at_the_top_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match=r"expected keys and values at the top level"):
        load(tmp_path, "- lookback_days\n")


def test_the_example_file_lists_every_default():
    assert SettingsFile(EXAMPLE).load() == Settings()


def test_a_bad_settings_file_stops_the_command_as_a_setup_error(tmp_path, monkeypatch, capsys):
    (tmp_path / "settings.yaml").write_text("top_n: 3\n")
    monkeypatch.setattr(Cli, "LOCAL", tmp_path)
    assert Cli.start() == 2
    assert capsys.readouterr().out.startswith("Could not set up the run: ")
