import json
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from fakes import FakePrompter, MemoryPendingLog, MemoryWarningLog, job

from job_radar.checkpoints import FileCheckpoints
from job_radar.classify import LlmClassifier
from job_radar.extract import LlmExtractor
from job_radar.history import FileRunHistory
from job_radar.llm import ClaudeCli, LlmError, UsageLimit
from job_radar.model import CandidateProfile, Job, Recommendation, Window
from job_radar.ranking import LlmRanker
from job_radar.report_renderer import MarkdownRenderer
from job_radar.steps.carried_over import CarriedOverStep
from job_radar.steps.classify import ClassifyStep
from job_radar.steps.recommend import RecommendTopJobsStep
from job_radar.usage import (
    FilePendingLog,
    LastRunPending,
    LimitStopped,
    UsageLimitGuard,
    UsageLimitReached,
)
from job_radar.words import Words

PROFILE = CandidateProfile(cv="A CV.", preferences="A job.")


class Runner:
    """A fake `claude` that answers with a set error result."""

    def __init__(self, text: str):
        self._text = text

    def __call__(self, args, **kwargs) -> subprocess.CompletedProcess:
        out = json.dumps({"type": "result", "is_error": True, "result": self._text})
        return subprocess.CompletedProcess(args, 1, out, "")


def test_a_usage_limit_answer_is_told_apart_from_other_errors():
    with pytest.raises(UsageLimit, match="usage limit reached"):
        ClaudeCli("haiku", run=Runner("Claude AI usage limit reached|1763000000")).complete(
            "s", "p"
        )
    with pytest.raises(LlmError) as error:
        ClaudeCli("haiku", run=Runner("Internal server error")).complete("s", "p")
    assert not isinstance(error.value, UsageLimit)


class LimitAfter:
    """A model that answers the first `n` prompts, then hits the usage limit."""

    def __init__(self, n: int, answer):
        self._left, self._answer, self.prompts = n, answer, 0

    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str:
        if self._left == 0:
            raise UsageLimit("usage limit reached")
        self._left -= 1
        self.prompts += 1
        return self._answer(re.findall(r'<job id="(j\d+)">', prompt))


def jobs(n: int) -> list[Job]:
    """N distinct jobs."""
    return [job(str(i), f"Engineer {i}") for i in range(n)]


def scores(ids):
    return json.dumps({"scores": [{"id": i, "score": 60, "reason": "Fits."} for i in ids]})


def labels(ids):
    rows = [
        {"id": i, "seniority": "senior", "job_type": None, "domain": None, "sector": None}
        for i in ids
    ]
    return json.dumps({"labels": rows})


def requirements(ids):
    return json.dumps({"jobs": [{"id": i, "requirements": []} for i in ids]})


def test_each_llm_pass_says_what_it_did_and_what_it_didnt_reach():
    with pytest.raises(UsageLimitReached) as ranked:
        LlmRanker(LimitAfter(1, scores), batch_size=2).score(jobs(5), PROFILE)
    assert len(ranked.value.done) == 2 and len(ranked.value.left) == 3
    with pytest.raises(UsageLimitReached) as labelled:
        LlmClassifier(LimitAfter(1, labels), 2, 100, {"e": "x"}, {"d": "y"}).classify(jobs(5))
    assert len(labelled.value.done) == 2 and [j.id for j in labelled.value.left][0] == "demo:2"
    with pytest.raises(UsageLimitReached) as read:
        LlmExtractor(LimitAfter(1, requirements), 2, 100).extract(jobs(5))
    assert len(read.value.done) == 2 and len(read.value.left) == 3


def test_finishing_carries_the_rest_over_and_stopping_fails_the_step():
    pending = MemoryPendingLog()
    finish = UsageLimitGuard(FakePrompter("f"), pending, MemoryWarningLog())
    left = jobs(3)

    def limited(_):
        raise UsageLimitReached(["done"], left)

    assert finish.run(limited, jobs(4), "ranked") == (["done"], left)
    assert pending.jobs() == left
    stop = UsageLimitGuard(FakePrompter("s"), MemoryPendingLog(), MemoryWarningLog())
    with pytest.raises(LimitStopped, match="run the same command after it resets"):
        stop.run(limited, jobs(4), "ranked")


def test_the_question_says_how_many_and_enter_means_finish():
    prompter = FakePrompter("f")

    def limited(_):
        raise UsageLimitReached({}, jobs(3))

    UsageLimitGuard(prompter, MemoryPendingLog(), MemoryWarningLog()).run(
        limited, jobs(5), "labelled"
    )
    assert prompter.asked == [
        "3 jobs not labelled: usage limit reached. "
        "Finish with what's done and carry them over, or stop?"
    ]


def test_a_step_hit_by_the_limit_passes_on_only_the_jobs_it_finished():
    pending = MemoryPendingLog()
    guard = UsageLimitGuard(FakePrompter("f"), pending, MemoryWarningLog())
    classifier = LlmClassifier(LimitAfter(1, labels), 2, 100, {"e": "x"}, {"d": "y"})
    kept = ClassifyStep(classifier, FakePrompter(), guard, MemoryWarningLog()).run(jobs(5))
    assert [j.id for j in kept] == ["demo:0", "demo:1"]
    assert [j.id for j in pending.jobs()] == ["demo:2", "demo:3", "demo:4"]


def test_recommend_keeps_the_scores_it_got_before_the_limit():
    guard = UsageLimitGuard(FakePrompter("f"), MemoryPendingLog(), MemoryWarningLog())
    ranker = LlmRanker(LimitAfter(1, scores), batch_size=2)
    step = RecommendTopJobsStep(ranker, PROFILE, 10, 40, guard, MemoryWarningLog())
    top = step.run(jobs(5))
    assert all(isinstance(rec, Recommendation) for rec in top) and len(top) == 2


def test_the_pending_file_keeps_each_job_once_and_survives_a_completed_run(tmp_path):
    log = FilePendingLog(tmp_path)
    log.add(jobs(2))
    log.add(jobs(3))
    assert [j.id for j in log.jobs()] == ["demo:0", "demo:1", "demo:2"]
    checkpoints = FileCheckpoints(tmp_path, Window(start=date(2026, 11, 8), end=date(2026, 11, 9)))
    checkpoints.save("report", [])
    checkpoints.complete()
    assert (tmp_path / "pending.jsonl").is_file()


def run(runs: Path, name: str, end: date, carried: list[Job], completed: bool = True) -> None:
    """A run folder that ended on that day and carried these jobs over."""
    folder = runs / name
    folder.mkdir(parents=True)
    FilePendingLog(folder).add(carried)
    checkpoints = FileCheckpoints(folder, Window(start=end - timedelta(days=1), end=end))
    checkpoints.save("report", [])
    if completed:
        checkpoints.complete()


def test_the_next_run_reads_what_the_last_completed_run_carried_over(tmp_path):
    run(tmp_path, "2026-11-08T09-00-00", date(2026, 11, 8), jobs(1))
    run(tmp_path, "2026-11-09T09-00-00", date(2026, 11, 9), jobs(3)[1:])
    run(tmp_path, "2026-11-09T10-00-00", date(2026, 11, 9), jobs(5), completed=False)
    pending = LastRunPending(FileRunHistory(tmp_path, MemoryWarningLog()), tmp_path).jobs()
    assert [j.id for j in pending] == ["demo:1", "demo:2"]


def test_carried_over_jobs_join_unless_this_run_found_them_again():
    class Carried:
        def jobs(self):
            return jobs(3)

    found_again = jobs(3)[1]
    added = CarriedOverStep(Carried()).run([found_again, job("9", "Designer")])
    assert [j.id for j in added] == ["demo:1", "demo:9", "demo:0", "demo:2"]


def test_the_report_says_how_many_jobs_were_carried_over():
    from job_radar.model import ReportContent

    window = Window(start=date(2026, 11, 8), end=date(2026, 11, 9))
    content = ReportContent(
        run="r", window=window, min_score=40, recommendations=(), funnel=(), carried_over=3
    )
    text = MarkdownRenderer(Words()).render(content)
    assert "3 jobs carried over to the next run (usage limit)." in text
