import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fakes import EXAMPLE, FakePrompter

from job_radar.app.app_factory import AppFactory
from job_radar.config.secrets import EnvSecrets
from job_radar.config.settings import SettingsFile
from job_radar.config.yaml_file import ConfigError
from job_radar.matching.place_codes import PlaceCodes
from job_radar.models import (
    IfMissing,
    MinSalary,
    Period,
    Places,
    RawPage,
    Search,
    SearchCriteria,
    Window,
    WorkMode,
    WorkModes,
)
from job_radar.sources.board_client import BoardClient
from job_radar.sources.jobspipe import JobsPipeError, JobsPipeParser, JobsPipeSource
from job_radar.utils.html_text import HtmlText

FIXTURE = Path(__file__).parent / "fixtures" / "jobspipe" / "search_page.json"
WINDOW = Window(start=date(2026, 11, 8), end=date(2026, 11, 9))
PARSER = JobsPipeParser(PlaceCodes(), HtmlText())


def postings():
    """The recorded page, parsed."""
    return PARSER.parse(RawPage(source="jobspipe", page=1, body=FIXTURE.read_text()))


def test_parse_reads_every_job_on_the_page():
    found = postings()
    assert [p.company for p in found] == [
        "Uber",
        "Smithsonian Institution",
        "Ramp",
        "Intuitive",
        "Utah Association of Counties",
    ]
    assert all(p.source == "jobspipe" and p.description for p in found)


def test_parse_maps_a_full_record():
    uber = postings()[0]
    assert (uber.title, uber.source_id) == (
        "Staff Software Engineer, Agentic",
        "iaziqy.fa.ocs:304059",
    )
    assert [(p.text, p.country, p.region) for p in uber.locations] == [
        ("San Francisco, CA, United States", "US", "US-CA")
    ]
    assert uber.work_mode is WorkMode.UNKNOWN
    assert (uber.salary.min, uber.salary.max, uber.salary.currency, uber.salary.period) == (
        Decimal(232000),
        Decimal(258000),
        "USD",
        Period.YEAR,
    )
    assert uber.posted_at == date(2026, 11, 9)


def test_parse_reads_work_modes_and_missing_pay():
    _, smithsonian, ramp, intuitive, _ = postings()
    assert (smithsonian.work_mode, smithsonian.locations[0].region) == (WorkMode.ONSITE, "US-DC")
    assert (ramp.work_mode, ramp.locations[0].country) == (WorkMode.REMOTE, "US")
    assert ramp.url.startswith("https://jobs.ashbyhq.com/ramp/")
    assert intuitive.salary is None


def test_the_fixture_has_no_contact_details_left():
    text = FIXTURE.read_text()
    emails = {e for e in __import__("re").findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)}
    assert emails <= {"someone@example.org"}


SEARCH = Search(
    name="remote-us",
    roles=("engineer", "developer"),
    exclude_titles=("civil",),
    work_mode=WorkModes(values=(WorkMode.REMOTE,)),
    locations=Places(values=("US", "US-WA"), if_missing=IfMissing.DROP),
    min_salary=MinSalary(amount=Decimal(70), period=Period.HOUR),
)


def source(handler, filters=None, max_jobs=25, prompter=None) -> JobsPipeSource:
    """A source over a fake API, with no pauses."""
    client = BoardClient(httpx.Client(transport=httpx.MockTransport(handler)), 0, lambda s: None)
    return JobsPipeSource(client, filters or {}, (max_jobs, None), prompter or FakePrompter())


def test_query_sends_each_criterion_and_asks_for_unknowns_a_criterion_keeps():
    body = source(
        lambda r: None, filters={"max_ghost_score": 40, "include_unknown": ["seniority"]}
    ).query(SEARCH, WINDOW)
    assert body == {
        "posted_at_gte": "2026-11-08",
        "job_title_or": ["engineer", "developer"],
        "job_title_not": ["civil"],
        "work_arrangement_or": ["remote"],
        "job_country_code_or": ["US"],
        "region_or": ["US-WA"],
        "min_salary_usd": 145600,
        "max_ghost_score": 40,
        "include_unknown": ["work_arrangement", "salary", "seniority"],
    }


class FakeApi:
    """JobsPipe over MockTransport: the account, then pages of a set size with cursors."""

    def __init__(self, total: int, status: int = 200):
        self.total, self.status, self.bodies = total, status, []
        self.served = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/account":
            return httpx.Response(200, json={"credits_remaining": 100, "credits_used": 40})
        if request.url.path == "/v1/jobs/export/estimate":
            if self.status == 504:
                return httpx.Response(504, json={"error": "Job search timed out."})
            return httpx.Response(200, json={"rows": self.total})
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "bad", "message": "No credits left."})
        body = json.loads(request.content)
        self.bodies.append(body)
        count = min(body["limit"], self.total - self.served)
        data = [
            {"id": str(self.served + n), "job_title": "Engineer", "company": "Acme"}
            for n in range(count)
        ]
        self.served += count
        cursor = "more" if self.served < self.total else None
        meta = {
            "credits_charged": count,
            "credits_remaining": 100 - self.served,
            "next_cursor": cursor,
        }
        return httpx.Response(200, json={"metadata": meta, "data": data})


def test_fetch_pages_with_the_cursor_up_to_the_cap():
    api, prompter = FakeApi(total=30), FakePrompter()
    pages = source(api, max_jobs=30, prompter=prompter).fetch(
        SearchCriteria(searches=(SEARCH,)), WINDOW
    )
    assert [b["limit"] for b in api.bodies] == [25, 5]
    assert "cursor" not in api.bodies[0] and api.bodies[1]["cursor"] == "more"
    assert [p.page for p in pages] == [1, 2]
    assert prompter.told == ["JobsPipe: 30 jobs, 30 credits used, 70 left."]


def test_a_fetch_is_never_partial():
    # Acceptance (Cost): a fetch is never partial: a source is fetched in full or not at all.
    api, prompter = FakeApi(total=100), FakePrompter()
    with pytest.raises(JobsPipeError) as over:
        source(api, max_jobs=30, prompter=prompter).fetch_paid(
            SearchCriteria(searches=(SEARCH,)), WINDOW, cap=30
        )
    assert str(over.value) == (
        "found more jobs than the 30 approved, so none are used, as a fetch is all or nothing "
        "(30 credits used; jobs paid for are free again this month)"
    )
    assert prompter.told == ["JobsPipe: 30 jobs, 30 credits used, 70 left."]


def test_a_search_the_cap_leaves_unasked_fails_the_fetch_too():
    api = FakeApi(total=100)
    with pytest.raises(JobsPipeError, match="more jobs than the 25 approved"):
        source(api).fetch_paid(TWO, WINDOW, cap=25)
    assert len(api.bodies) == 1


def test_a_cap_of_nothing_fetches_nothing():
    api = FakeApi(total=5)
    assert source(api).fetch_paid(TWO, WINDOW, cap=0).pages == ()
    assert api.bodies == []


def test_fetch_stops_when_the_results_run_out():
    api = FakeApi(total=3)
    two = SearchCriteria(searches=(SEARCH, SEARCH.model_copy(update={"name": "seattle"})))
    pages = source(api).fetch(two, WINDOW)
    assert [len(json.loads(p.body)["data"]) for p in pages] == [3, 0]


def test_an_error_from_jobspipe_fails_with_its_message():
    with pytest.raises(JobsPipeError, match="^HTTP 402: No credits left.$"):
        source(FakeApi(total=5, status=402)).fetch(SearchCriteria(searches=(SEARCH,)), WINDOW)


def test_secrets_come_from_the_environment_first_then_the_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nJOBSPIPE_API_KEY="jp_live_file"\nOTHER=\n')
    secrets = EnvSecrets(env)
    monkeypatch.delenv("JOBSPIPE_API_KEY", raising=False)
    assert secrets.get("JOBSPIPE_API_KEY") == "jp_live_file"
    assert secrets.get("OTHER") is None and secrets.get("MISSING") is None
    monkeypatch.setenv("JOBSPIPE_API_KEY", "jp_live_env")
    assert secrets.get("JOBSPIPE_API_KEY") == "jp_live_env"
    assert EnvSecrets(tmp_path / "none").get("X") is None


def test_the_example_env_file_names_the_key_without_a_value(monkeypatch):
    monkeypatch.delenv("JOBSPIPE_API_KEY", raising=False)
    env = EXAMPLE / ".env"
    assert "JOBSPIPE_API_KEY=" in env.read_text()
    assert EnvSecrets(env).get("JOBSPIPE_API_KEY") is None


def test_jobspipe_on_without_a_key_is_a_setup_error(tmp_path):
    local = tmp_path / "config_local"
    local.mkdir()
    (local / "profile.yaml").write_text("searches: {all: {}}\n")
    (local / "cv.md").write_text("A CV.\n")
    (local / "preferences.md").write_text("A job.\n")
    factory = AppFactory(
        SettingsFile.defaults(output=str(tmp_path), sources={"jobspipe": {"enabled": True}}),
        local,
        EXAMPLE,
        None,
        FakePrompter(),
        {},
    )
    with pytest.raises(
        ConfigError, match="JOBSPIPE_API_KEY is not set: add it to config_local/.env"
    ):
        factory.create(demo=False)


def test_a_run_fetches_from_jobspipe_and_fast_forward(tmp_path, monkeypatch):
    # Acceptance (Job search): a run fetches from JobsPipe and Fast Forward (JobsPipe on).
    from job_radar.llm.llm import ClaudeCli

    monkeypatch.setattr(ClaudeCli, "check", lambda self: None)
    local = tmp_path / "config_local"
    local.mkdir()
    (local / "profile.yaml").write_text("searches: {all: {}}\n")
    (local / "cv.md").write_text("A CV.\n")
    (local / "preferences.md").write_text("A job.\n")
    factory = AppFactory(
        SettingsFile.defaults(output=str(tmp_path), sources={"jobspipe": {"enabled": True}}),
        local,
        EXAMPLE,
        None,
        FakePrompter(),
        {"JOBSPIPE_API_KEY": "jp_test"},
    )
    parts = factory._real()
    assert [s.name for s in parts.sources] == ["getro", "jobspipe"]
    assert [p.source for p in parts.parsers] == ["getro", "jobspipe"]


@pytest.mark.live
def test_live_estimate_answers_for_free():
    key = EnvSecrets(Path("config_local") / ".env").get("JOBSPIPE_API_KEY")
    if not key:
        pytest.skip("no JOBSPIPE_API_KEY")
    response = httpx.post(
        "https://api.jobspipe.dev/v1/jobs/export/estimate",
        json={"job_title_or": ["software engineer"], "posted_at_max_age_days": 1},
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    )
    assert response.status_code == 200 and isinstance(response.json()["rows"], int)


def test_with_match_if_missing_off_no_unknowns_are_asked_for():
    client = BoardClient(httpx.Client(), 0, lambda s: None)
    strict = JobsPipeSource(client, {}, (25, None), FakePrompter(), match_if_missing=False)
    assert "include_unknown" not in strict.query(SEARCH, WINDOW)


TWO = SearchCriteria(searches=(SEARCH, SEARCH.model_copy(update={"name": "seattle"})))


def test_plan_adds_up_free_estimates_and_reads_the_credits():
    plan = source(FakeApi(total=12), max_jobs=25).plan(TWO, WINDOW)
    assert (plan.estimate, plan.estimated, plan.credits_left) == (24, True, 100)
    assert (plan.per_run_max, plan.budget_left) == (25, 100)


def test_a_monthly_budget_is_what_the_month_has_left():
    client = BoardClient(
        httpx.Client(transport=httpx.MockTransport(FakeApi(total=1))), 0, lambda s: None
    )
    paid = JobsPipeSource(client, {}, (2500, 10_000), FakePrompter())
    assert paid.plan(TWO, WINDOW).budget_left == 10_000 - 40


def test_when_jobspipe_cant_count_the_estimate_is_the_per_run_max():
    plan = source(FakeApi(total=5, status=504), max_jobs=25).plan(TWO, WINDOW)
    assert (plan.estimate, plan.estimated) == (25, False)


def test_fetch_paid_spends_within_the_cap_and_says_what_it_cost():
    paid = source(FakeApi(total=10), max_jobs=250).fetch_paid(TWO, WINDOW, cap=20)
    assert (paid.charged, paid.credits_left) == (10, 90)
    assert sum(len(json.loads(p.body)["data"]) for p in paid.pages) == 10


def test_jobspipe_limits_come_from_the_plan_unless_the_settings_set_them():
    assert JobsPipeSource.PLANS["free"] == (250, None)
    assert JobsPipeSource.PLANS["seeker"] == (2500, 10_000)


def test_a_domain_the_settings_dont_define_is_a_setup_error(tmp_path):
    local = tmp_path / "config_local"
    local.mkdir()
    (local / "profile.yaml").write_text("searches: {all: {domains: [space]}}\n")
    factory = AppFactory(
        SettingsFile.defaults(output=str(tmp_path)), local, EXAMPLE, None, FakePrompter(), {}
    )
    with pytest.raises(
        ConfigError, match=r"searches.all.domains: unknown space; the settings define"
    ):
        factory.create(demo=False)
