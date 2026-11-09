from pathlib import Path

import pytest

from job_radar.model import Search, SearchCriteria
from job_radar.searches import SearchesFile
from job_radar.yaml_file import ConfigError

EXAMPLE = Path(__file__).parent.parent / "examples" / "profile.example.yaml"


def load(tmp_path, text: str) -> SearchCriteria:
    """The searches from a profile file with this text."""
    path = tmp_path / "profile.yaml"
    path.write_text(text)
    return SearchesFile(path).load()


def test_reads_each_search_in_the_files_order(tmp_path):
    criteria = load(tmp_path, "searches:\n  b: {roles: [engineer]}\n  a: {roles: [architect]}\n")
    assert criteria == SearchCriteria(
        searches=(Search(name="b", roles=("engineer",)), Search(name="a", roles=("architect",)))
    )


def test_common_fills_in_what_a_search_leaves_out(tmp_path):
    text = "common: {roles: [engineer]}\nsearches:\n  one: {}\n  two: {roles: [tech lead]}\n"
    assert load(tmp_path, text).searches == (
        Search(name="one", roles=("engineer",)),
        Search(name="two", roles=("tech lead",)),
    )


def test_a_search_with_no_roles_anywhere_matches_every_title(tmp_path):
    assert load(tmp_path, "searches: {all: {}}\n").searches == (Search(name="all", roles=()),)


def test_no_file_is_an_error_pointing_at_the_example(tmp_path):
    with pytest.raises(ConfigError, match=r"no .*profile.yaml: copy examples/profile.example.yaml"):
        SearchesFile(tmp_path / "profile.yaml").load()


def test_no_searches_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match=r"profile.yaml: searches: required"):
        load(tmp_path, "common: {roles: [engineer]}\n")


def test_a_criterion_not_supported_yet_is_an_unknown_key(tmp_path):
    with pytest.raises(ConfigError, match=r"searches.one.exclude_titles: unknown key"):
        load(tmp_path, "searches:\n  one: {exclude_titles: [intern]}\n")


def test_the_example_file_reads():
    names = [search.name for search in SearchesFile(EXAMPLE).load().searches]
    assert names == ["engineering", "leadership"]
