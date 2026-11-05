from fakes import REPORT, FakeStep, job

from job_radar.checkpoints import FileCheckpoints
from job_radar.model import StepCount
from job_radar.pipeline import Pipeline
from job_radar.result import RunFailed, RunSucceeded


def test_fresh_run_succeeds_with_the_report(tmp_path):
    steps = [FakeStep("dedupe", [job("1"), job("2")]), FakeStep("report", [REPORT])]
    result = Pipeline(steps, FileCheckpoints(tmp_path)).run()
    assert result == RunSucceeded(location=REPORT.location, summary=REPORT.summary)


def test_each_step_gets_the_previous_output(tmp_path):
    jobs = [job("1"), job("2")]
    first, second, last = FakeStep("a", jobs), FakeStep("b", jobs[:1]), FakeStep("c", [REPORT])
    Pipeline([first, second, last], FileCheckpoints(tmp_path)).run()
    assert first.received == []
    assert second.received == jobs
    assert last.received == jobs[:1]


def test_success_discards_outputs_and_keeps_funnel(tmp_path):
    steps = [FakeStep("dedupe", [job("1"), job("2")]), FakeStep("report", [REPORT])]
    Pipeline(steps, FileCheckpoints(tmp_path)).run()
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]
    assert FileCheckpoints(tmp_path).funnel() == [
        StepCount(step="dedupe", count=2),
        StepCount(step="report", count=1),
    ]


def test_failing_step_gives_run_failed_and_keeps_files(tmp_path):
    after = FakeStep("report", [REPORT])
    steps = [FakeStep("dedupe", [job("1")]), FakeStep("filter", error=ValueError("bad")), after]
    result = Pipeline(steps, FileCheckpoints(tmp_path)).run()
    assert result == RunFailed(step="filter", reason="bad")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dedupe.jsonl", "manifest.json"]
    assert after.received is None


def test_error_without_message_is_named_by_its_type(tmp_path):
    steps = [FakeStep("fetch", error=NotImplementedError())]
    result = Pipeline(steps, FileCheckpoints(tmp_path)).run()
    assert result == RunFailed(step="fetch", reason="NotImplementedError")


def test_last_step_without_a_report_fails(tmp_path):
    steps = [FakeStep("dedupe", [job("1")])]
    result = Pipeline(steps, FileCheckpoints(tmp_path)).run()
    assert result == RunFailed(step="dedupe", reason="the last step gave no report")
