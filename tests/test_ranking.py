import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fakes import MemoryDropLog, MemoryWarningLog, guard, job, posting

from job_radar.llm.job_ranker import BadAnswer, LlmRanker
from job_radar.matching.job_matcher import JobMatcher
from job_radar.matching.normalizer import Normalizer
from job_radar.models import CandidateProfile, Job, Period, Salary, Search, SearchCriteria, Window
from job_radar.pipeline.steps.filter import FilterStep
from job_radar.pipeline.steps.recommend import RecommendTopJobsStep

PROFILE = CandidateProfile(cv="Python engineer, 8 years.", preferences="Remote data roles.")


class FakeLlm:
    """A model that scores every job id in the prompt, or gives set answers first."""

    def __init__(self, *answers: str, score: int = 50):
        self._answers = list(answers)
        self._score = score
        self.prompts: list[str] = []
        self.schemas: list[dict | None] = []

    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if self._answers:
            return self._answers.pop(0)
        return answer(*ids_in(prompt), score=self._score)


def ids_in(prompt: str) -> list[str]:
    return re.findall(r'<job id="(j\d+)">', prompt)


def answer(*ids: str, score: int = 50) -> str:
    return json.dumps(
        {"scores": [{"id": i, "score": score, "reason": f"Reason {i}."} for i in ids]}
    )


def jobs(count: int) -> list[Job]:
    return [job(str(n), f"Engineer {n}") for n in range(1, count + 1)]


def test_sends_jobs_in_batches_and_keeps_their_order():
    llm = FakeLlm()
    recs = LlmRanker(llm, batch_size=2).score(jobs(5), PROFILE)
    assert [ids_in(p) for p in llm.prompts] == [["j1", "j2"], ["j1", "j2"], ["j1"]]
    assert [r.job.postings[0].title for r in recs] == [f"Engineer {n}" for n in range(1, 6)]
    assert all(schema == LlmRanker.SCHEMA for schema in llm.schemas)


def test_maps_each_score_and_reason_to_its_job():
    reply = json.dumps(
        {
            "scores": [
                {"id": "j2", "score": 90, "reason": "Strong fit,\n  remote."},
                {"id": "j1", "score": 10, "reason": "Wrong field."},
            ]
        }
    )
    recs = LlmRanker(FakeLlm(reply), batch_size=5).score(jobs(2), PROFILE)
    assert [(r.score, r.reason) for r in recs] == [
        (10, "Wrong field."),
        (90, "Strong fit, remote."),
    ]


def test_the_prompt_holds_the_profile_and_each_jobs_details():
    salaried = posting("1", "Data Engineer", source="getro").model_copy(
        update={
            "description": "Build pipelines.",
            "salary": Salary(
                min=Decimal("125000"), max=Decimal("140000"), currency="USD", period=Period.YEAR
            ),
        }
    )
    one = Job(id="a", keys=("a",), postings=(salaried,), first_seen=date(2026, 11, 5))
    llm = FakeLlm()
    LlmRanker(llm, batch_size=5).score([one, job("2", "Analyst")], PROFILE)
    prompt = llm.prompts[0]
    assert "<cv>\nPython engineer, 8 years.\n</cv>" in prompt
    assert "<preferences>\nRemote data roles.\n</preferences>" in prompt
    assert "Title: Data Engineer\nCompany: Example Org\nPlaces: Remote\nWork mode: remote" in prompt
    assert "Salary: 125,000 to 140,000 USD a year\nDescription:\nBuild pipelines." in prompt
    assert "Salary: not given\nDescription:\n(no description)" in prompt


def test_long_descriptions_are_cut():
    long = posting("1").model_copy(update={"description": "word " * 100})
    one = Job(id="a", keys=("a",), postings=(long,), first_seen=date(2026, 11, 5))
    llm = FakeLlm()
    LlmRanker(llm, batch_size=5, description_chars=20).score([one], PROFILE)
    assert "Description:\nword word word word [cut]\n</job>" in llm.prompts[0]


@pytest.mark.parametrize(
    ("bad", "problem"),
    [
        ("not json at all", "not the expected JSON"),
        (answer("j1"), "missing: j2"),
        (answer("j1", "j2", "j3"), "unknown: j3"),
        (answer("j1", "j1", "j2"), "twice: j1"),
        (answer("j1", "j2", score=101), "not the expected JSON"),
    ],
)
def test_a_bad_answer_is_asked_again_with_what_was_wrong(bad, problem):
    llm = FakeLlm(bad)
    recs = LlmRanker(llm, batch_size=5).score(jobs(2), PROFILE)
    assert len(recs) == 2
    assert len(llm.prompts) == 2
    assert problem in llm.prompts[1]
    assert llm.prompts[1].startswith(llm.prompts[0])


def test_a_second_bad_answer_splits_the_batch_and_a_job_that_still_fails_is_left_out():
    llm = FakeLlm(answer("j1"), answer("j1"), answer("j1"), "nope", "nope")
    recs = LlmRanker(llm, batch_size=5).score(jobs(2), PROFILE)
    assert [rec.job.id for rec in recs] == ["demo:1"]
    assert len(llm.prompts) == 5
    assert ids_in(llm.prompts[2]) == ["j1"] and "Engineer 2" in llm.prompts[3]


def test_a_bad_answer_names_what_was_wrong():
    with pytest.raises(BadAnswer, match="missing: j2"):
        LlmRanker(FakeLlm(), batch_size=5)._read(answer("j1"), {"j1": job("1"), "j2": job("2")})


def test_no_jobs_asks_nothing():
    llm = FakeLlm()
    assert LlmRanker(llm, batch_size=5).score([], PROFILE) == []
    assert llm.prompts == []


def test_only_filtered_postings_go_to_the_llm_in_batches():
    """Acceptance (Runs): only filtered postings go to the LLM, in batches."""
    window = Window(start=date(2026, 10, 22), end=date(2026, 11, 5))
    search = SearchCriteria(searches=(Search(name="default", roles=("data engineer",)),))
    found = [
        job(str(n), title)
        for n, title in enumerate(
            [
                "Data Engineer",
                "Grants Coordinator",
                "Senior Data Engineer",
                "Designer",
                "Data Engineer II",
            ],
            start=1,
        )
    ]
    kept = FilterStep(search, window, JobMatcher(Normalizer()), MemoryDropLog()).run(found)
    llm = FakeLlm()
    RecommendTopJobsStep(
        LlmRanker(llm, batch_size=2),
        PROFILE,
        top_n=10,
        min_score=0,
        guard=guard(),
        warnings=MemoryWarningLog(),
    ).run(kept)
    titles = [re.findall(r"Title: (.+)", prompt) for prompt in llm.prompts]
    assert titles == [["Data Engineer", "Senior Data Engineer"], ["Data Engineer II"]]
