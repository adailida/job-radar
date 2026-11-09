from decimal import Decimal
from pathlib import Path

import pytest

from job_radar.model import (
    IfMissing,
    MinSalary,
    Period,
    Places,
    Search,
    SearchCriteria,
    WorkMode,
    WorkModes,
)
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
    with pytest.raises(ConfigError, match=r"searches.one.keywords: unknown key"):
        load(tmp_path, "searches:\n  one: {keywords: [python]}\n")


def test_reads_every_criterion_in_short_and_full_form(tmp_path):
    text = """
common:
  roles: [engineer]
  exclude_titles: [civil]
  min_salary: 150000
searches:
  remote-us:
    work_mode: [remote]
    locations: {values: [US], if_missing: drop}
  seattle:
    locations: [US-WA]
    min_salary: {amount: 70, period: hour, if_missing: drop}
"""
    remote, seattle = load(tmp_path, text).searches
    assert remote == Search(
        name="remote-us",
        roles=("engineer",),
        exclude_titles=("civil",),
        work_mode=WorkModes(values=(WorkMode.REMOTE,)),
        locations=Places(values=("US",), if_missing=IfMissing.DROP),
        min_salary=MinSalary(amount=Decimal(150000)),
    )
    assert seattle.locations == Places(values=("US-WA",))
    assert seattle.min_salary == MinSalary(
        amount=Decimal(70), period=Period.HOUR, if_missing=IfMissing.DROP
    )


@pytest.mark.parametrize(
    ("line", "problem"),
    [
        (
            "locations: [Seattle]",
            r"searches.one.locations: not ISO codes like US or US-WA: Seattle",
        ),
        (
            "work_mode: [unknown]",
            r"searches.one.work_mode: work modes are remote, hybrid or onsite",
        ),
        ("work_mode: [anywhere]", r"searches.one.work_mode.values.0: input should be"),
        ("locations: {values: [US], if_missing: maybe}", r"locations.if_missing: input should be"),
    ],
)
def test_a_bad_criterion_names_its_path(tmp_path, line, problem):
    with pytest.raises(ConfigError, match=problem):
        load(tmp_path, f"searches:\n  one: {{{line}}}\n")


def test_the_example_file_reads():
    names = [search.name for search in SearchesFile(EXAMPLE).load().searches]
    assert names == ["remote-us", "nyc-office"]


def test_reads_seniority_and_domains(tmp_path):
    text = (
        "searches:\n"
        "  one: {seniority: [senior, lead], domains: {values: [climate], if_missing: drop}}\n"
    )
    [one] = load(tmp_path, text).searches
    assert [level.value for level in one.seniority.values] == ["senior", "lead"]
    assert (one.domains.values, one.domains.if_missing) == (("climate",), IfMissing.DROP)


def test_unknown_is_not_a_level_to_ask_for(tmp_path):
    with pytest.raises(ConfigError, match=r"searches.one.seniority: ask for levels"):
        load(tmp_path, "searches:\n  one: {seniority: [unknown]}\n")
