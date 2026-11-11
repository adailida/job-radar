import json

import pytest
from fakes import EXAMPLE, FakePrompter, FixedClock, MemoryPendingLog, MemoryWarningLog, job

from job_radar.app.app_factory import AppFactory
from job_radar.cli import Cli
from job_radar.config.settings import SettingsFile
from job_radar.models import Alert, AlertCode
from job_radar.pipeline.steps.llm_cap import CapStopped, LlmCapStep
from job_radar.storage.pending_log import FilePendingLog

FIRST_RUN = "2026-11-05T10-00-00"
QUESTION = "5 jobs would go to Claude, over the cap of 3. Send them all, only the first 3, or stop?"


def jobs(n: int):
    """N distinct jobs, in order."""
    return [job(str(i), f"Engineer {i}") for i in range(n)]


def cap_step(*answers: str, cap: int = 3):
    """The cap step with a user giving these answers, and its prompter, pending log and warnings."""
    prompter, pending, warnings = FakePrompter(*answers), MemoryPendingLog(), MemoryWarningLog()
    return LlmCapStep(cap, prompter, pending, warnings), prompter, pending, warnings


def test_under_the_cap_every_job_goes_on_and_nothing_is_asked():
    step, prompter, pending, warnings = cap_step()
    assert step.run(jobs(3)) == jobs(3)
    assert step.run([]) == []
    assert prompter.asked == [] and pending.jobs() == [] and warnings.alerts() == []


def test_over_the_cap_the_question_says_how_many_and_enter_means_the_first_ones():
    step, prompter, _, _ = cap_step("f")
    step.run(jobs(5))
    assert prompter.asked == [QUESTION]


def test_over_the_cap_all_sends_every_job_and_carries_nothing_over():
    step, _, pending, warnings = cap_step("a")
    assert step.run(jobs(5)) == jobs(5)
    assert pending.jobs() == [] and warnings.alerts() == []


def test_over_the_cap_first_sends_the_first_ones_and_carries_the_rest_over_with_a_warning():
    step, _, pending, warnings = cap_step("f")
    assert step.run(jobs(5)) == jobs(3)
    assert pending.jobs() == jobs(5)[3:]
    assert warnings.alerts() == [
        Alert(
            code=AlertCode.LLM_CAPPED,
            message="Over the LLM cap: 2 of 5 jobs not sent to Claude, carried over to the "
            "next run (llm.ask_above_jobs is 3).",
        )
    ]


def test_over_the_cap_stop_fails_the_step_and_carries_nothing_over():
    step, _, pending, warnings = cap_step("s")
    with pytest.raises(CapStopped, match="stopped before sending 5 jobs to Claude"):
        step.run(jobs(5))
    assert pending.jobs() == [] and warnings.alerts() == []


def capped_cli(tmp_path, prompter: FakePrompter, hour: int = 10, cap: int = 3) -> Cli:
    """The real demo command with a low LLM cap: the demo's 5 jobs are over it."""
    settings = SettingsFile.defaults(
        output=str(tmp_path), recommend={"top_n": 3}, llm={"ask_above_jobs": cap}
    )
    return Cli(
        AppFactory(settings, tmp_path / "config_local", EXAMPLE, FixedClock(hour), prompter, {})
    )


def counts(folder) -> dict[str, int]:
    """Each finished step of a run and its count, from its manifest."""
    manifest = json.loads((folder / "manifest.json").read_text())
    return {step["step"]: step["count"] for step in manifest["steps"]}


def test_a_capped_run_carries_the_rest_over_in_pending_jsonl_and_the_next_run_takes_them(tmp_path):
    prompter = FakePrompter(True, "f")
    assert capped_cli(tmp_path, prompter).main(["run", "--demo"]) == 0
    assert prompter.asked[-1].startswith("5 jobs would go to Claude, over the cap of 3.")
    folder = tmp_path / "demo" / FIRST_RUN
    assert len(FilePendingLog(folder).jobs()) == 2
    assert "pending.jsonl" in [p.name for p in folder.iterdir()]
    assert (counts(folder)["describe"], counts(folder)["llm_cap"]) == (5, 3)
    report = (folder / "report.md").read_text()
    assert "2 jobs carried over to the next run (usage limit or LLM cap)." in report
    assert "- Over the LLM cap: 2 of 5 jobs not sent to Claude" in report
    assert capped_cli(tmp_path, FakePrompter(), hour=15).main(["run", "--demo"]) == 0
    later = counts(tmp_path / "demo" / "2026-11-05T15-00-00")
    # This run finds both carried-over jobs again, as new: each joins once.
    assert (later["filter"], later["carried_over"], later["llm_cap"]) == (2, 2, 2)


def test_stopping_at_the_cap_fails_the_run_before_any_llm_step_and_it_resumes(tmp_path, capsys):
    assert capped_cli(tmp_path, FakePrompter(True, "s")).main(["run", "--demo"]) == 1
    assert "Run failed at step 'llm_cap': stopped before sending 5 jobs" in capsys.readouterr().out
    folder = tmp_path / "demo" / FIRST_RUN
    assert list(counts(folder))[-1] == "describe"
    assert not (folder / "pending.jsonl").exists()
    resumed = FakePrompter(True, "a")
    assert capped_cli(tmp_path, resumed, hour=15).main(["run", "--demo"]) == 0
    assert resumed.asked[-1].startswith("5 jobs would go to Claude")
    assert counts(folder)["classify"] == 5
