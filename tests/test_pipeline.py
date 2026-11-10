from fakes import REPORT, WINDOW, FakeStep, job

from job_radar.checkpoints import FileCheckpoints
from job_radar.error_log import FileErrorLog
from job_radar.model import StepCount
from job_radar.pipeline import Pipeline
from job_radar.result import RunFailed, RunSucceeded


def test_fresh_run_succeeds_with_the_report(tmp_path):
    steps = [FakeStep("dedupe", [job("1"), job("2")]), FakeStep("report", [REPORT])]
    result = Pipeline(steps, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert result == RunSucceeded(location=REPORT.location, summary=REPORT.summary)


def test_each_step_gets_the_previous_output(tmp_path):
    jobs = [job("1"), job("2")]
    first, second, last = FakeStep("a", jobs), FakeStep("b", jobs[:1]), FakeStep("c", [REPORT])
    Pipeline([first, second, last], FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert first.received == []
    assert second.received == jobs
    assert last.received == jobs[:1]


def test_success_completes_the_run_and_keeps_funnel(tmp_path):
    steps = [FakeStep("dedupe", [job("1"), job("2")]), FakeStep("report", [REPORT])]
    Pipeline(steps, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]
    assert FileCheckpoints(tmp_path, WINDOW).funnel() == [
        StepCount(step="dedupe", count=2),
        StepCount(step="report", count=1),
    ]


def test_failing_step_gives_run_failed_and_keeps_files(tmp_path):
    after = FakeStep("report", [REPORT])
    steps = [FakeStep("dedupe", [job("1")]), FakeStep("filter", error=ValueError("bad")), after]
    result = Pipeline(steps, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    log = str(tmp_path / "error.log")
    assert result == RunFailed(step="filter", reason="ValueError: bad", details=log)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "01-dedupe.jsonl",
        "error.log",
        "manifest.json",
    ]
    assert after.received is None


def test_error_without_message_is_named_by_its_type(tmp_path):
    steps = [FakeStep("fetch", error=NotImplementedError())]
    result = Pipeline(steps, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert result == RunFailed(
        step="fetch", reason="NotImplementedError", details=str(tmp_path / "error.log")
    )


def test_last_step_without_a_report_fails(tmp_path):
    steps = [FakeStep("dedupe", [job("1")])]
    result = Pipeline(steps, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert result == RunFailed(step="dedupe", reason="the last step gave no report")


def test_a_resumed_run_skips_saved_steps_and_reads_the_last_one_back(tmp_path):
    jobs = [job("1"), job("2")]
    first = Pipeline(
        [FakeStep("dedupe", jobs), FakeStep("filter", error=ValueError("bad"))],
        FileCheckpoints(tmp_path, WINDOW),
        FileErrorLog(tmp_path),
    ).run()
    assert first.reason == "ValueError: bad"
    again = [
        FakeStep("dedupe", [job("9")]),
        FakeStep("filter", jobs[:1]),
        FakeStep("report", [REPORT]),
    ]
    result = Pipeline(again, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert result == RunSucceeded(location=REPORT.location, summary=REPORT.summary)
    assert again[0].received is None
    assert again[1].received == jobs
    assert FileCheckpoints(tmp_path, WINDOW).funnel() == [
        StepCount(step="dedupe", count=2),
        StepCount(step="filter", count=1),
        StepCount(step="report", count=1),
    ]


def test_a_run_saved_to_the_end_but_not_completed_completes_on_resume(tmp_path):
    checkpoints = FileCheckpoints(tmp_path, WINDOW)
    checkpoints.save("report", [REPORT])
    report = FakeStep("report", [REPORT])
    result = Pipeline([report], FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert result == RunSucceeded(location=REPORT.location, summary=REPORT.summary)
    assert report.received is None


def test_a_saved_output_that_cant_be_read_fails_the_resume(tmp_path):
    FileCheckpoints(tmp_path, WINDOW).save("dedupe", [job("1")])
    (tmp_path / "01-dedupe.jsonl").write_text("not json\n")
    steps = [FakeStep("dedupe", [job("1")]), FakeStep("report", [REPORT])]
    result = Pipeline(steps, FileCheckpoints(tmp_path, WINDOW), FileErrorLog(tmp_path)).run()
    assert isinstance(result, RunFailed) and result.step == "dedupe"
    assert result.reason.startswith("can't read its saved output")
