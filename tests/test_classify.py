import json
import re

import pytest
from fakes import FakePrompter, MemoryWarningLog, guard, job

from job_radar.classify import LlmClassifier, TitleClassifier
from job_radar.matching import JobMatcher
from job_radar.model import (
    Alert,
    AlertCode,
    Classification,
    Domains,
    IfMissing,
    Job,
    Search,
    SearchCriteria,
    Seniorities,
    Seniority,
)
from job_radar.normalize import Normalizer
from job_radar.steps.classify import ClassifyStep
from job_radar.steps.match import MatchStep

JOB_TYPES = {"engineering": "builds software", "product": "product management"}
DOMAINS = {"climate": "climate change", "health": "health care"}


def labels(*ids: str, seniority="senior", job_type="engineering", domain="climate") -> str:
    """A model answer labelling these ids alike."""
    rows = [
        {"id": i, "seniority": seniority, "job_type": job_type, "domain": domain, "sector": "x"}
        for i in ids
    ]
    return json.dumps({"labels": rows})


class LabellingLlm:
    """A model that labels every id in the prompt, or gives set answers first."""

    def __init__(self, *answers: str):
        self._answers = list(answers)
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if self._answers:
            return self._answers.pop(0)
        return labels(*re.findall(r'<job id="(j\d+)">', prompt))


def classifier(llm, batch_size=50) -> LlmClassifier:
    """The classifier over this model, with short descriptions."""
    return LlmClassifier(llm, batch_size, 20, JOB_TYPES, DOMAINS)


def described(source_id: str, title: str, text: str = "We build things.") -> Job:
    """A job with a description."""
    one = job(source_id, title)
    posting = one.postings[0].model_copy(update={"description": text})
    return one.model_copy(update={"postings": (posting,)})


def test_labels_each_job_by_its_id():
    jobs = [described("1", "Senior Engineer"), described("2", "PM")]
    found = classifier(LabellingLlm()).classify(jobs)
    assert set(found) == {"demo:1", "demo:2"}
    assert found["demo:1"] == Classification(
        job_id="demo:1",
        seniority=Seniority.SENIOR,
        job_type="engineering",
        domain="climate",
        sector="x",
        prompt_version="classify-1",
    )


def test_the_prompt_lists_the_names_and_cuts_descriptions():
    llm = LabellingLlm()
    classifier(llm).classify([described("1", "Engineer", "A" * 50)])
    prompt = llm.prompts[0]
    assert "- engineering: builds software" in prompt and "- health: health care" in prompt
    assert "A" * 20 in prompt and "A" * 21 not in prompt
    items = llm.schemas[0]["properties"]["labels"]["items"]["properties"]
    assert items["domain"]["enum"] == ["climate", "health", "Other", None]


def test_a_name_not_on_the_list_becomes_other():
    llm = LabellingLlm(labels("j1", domain="space"))
    [found] = classifier(llm).classify([described("1", "Engineer")]).values()
    assert found.domain == "Other"


def test_a_bad_answer_is_asked_again_then_the_batch_is_split():
    llm = LabellingLlm(labels("j1"), labels("j1"))
    found = classifier(llm).classify([described("1", "A"), described("2", "B")])
    assert set(found) == {"demo:1", "demo:2"}
    assert "Your last answer could not be used: missing: j2" in llm.prompts[1]
    assert len(llm.prompts) == 4  # first, again, then each half


def test_a_job_that_keeps_failing_gets_no_labels():
    llm = LabellingLlm("not json", "not json")
    assert classifier(llm).classify([described("1", "A")]) == {}


def test_batches_go_a_set_number_at_a_time():
    llm = LabellingLlm()
    classifier(llm, batch_size=2).classify([described(str(n), "A") for n in range(5)])
    assert [len(re.findall("<job id", p)) for p in llm.prompts] == [2, 2, 1]


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Senior Data Engineer", Seniority.SENIOR),
        ("Staff Engineer", Seniority.LEAD),
        ("Engineering Manager, Data", Seniority.MANAGER),
        ("Data Engineer", Seniority.UNKNOWN),
    ],
)
def test_the_demo_classifier_reads_levels_from_titles(title, level):
    [found] = TitleClassifier().classify([job("1", title)]).values()
    assert found.seniority is level


class SetLabels:
    """A classifier with set labels by job id."""

    def __init__(self, found: dict):
        self._found = found

    def classify(self, jobs):
        return self._found


def label(job_id: str, seniority=Seniority.SENIOR, domain: str | None = "climate"):
    """Labels for one job."""
    return Classification(job_id=job_id, seniority=seniority, domain=domain, prompt_version="test")


def test_the_step_adds_labels_and_says_how_many_failed():
    prompter = FakePrompter()
    jobs = [job("1"), job("2")]
    warnings = MemoryWarningLog()
    step = ClassifyStep(SetLabels({"demo:1": label("demo:1")}), prompter, guard(), warnings)
    found = step.run(jobs)
    assert [j.classification for j in found] == [label("demo:1"), None]
    said = "The LLM couldn't label 1 of 2 jobs: their seniority and domain count as not given."
    assert prompter.told == [said]
    assert warnings.alerts() == [Alert(code=AlertCode.LLM_FAILED, message=said)]


MATCHER = JobMatcher(Normalizer())
SENIOR = Search(name="s", seniority=Seniorities(values=(Seniority.SENIOR, Seniority.LEAD)))
CLIMATE = Search(name="c", domains=Domains(values=("climate",), if_missing=IfMissing.DROP))


def labelled(job_id: str, **labels) -> Job:
    """A job with these labels."""
    return job(job_id).model_copy(update={"classification": label(f"demo:{job_id}", **labels)})


@pytest.mark.parametrize(
    ("one", "search", "miss"),
    [
        (job("1"), SENIOR, None),
        (labelled("1"), SENIOR, None),
        (labelled("1", seniority=Seniority.MID), SENIOR, "seniority"),
        (labelled("1", seniority=Seniority.UNKNOWN), SENIOR, None),
        (labelled("1", domain="health"), CLIMATE, "domain"),
        (labelled("1", domain=None), CLIMATE, "domain"),
        (labelled("1"), CLIMATE, None),
    ],
)
def test_seniority_and_domain_count_once_a_job_has_labels(one, search, miss):
    assert MATCHER.miss(one, search) == miss


def test_the_match_step_keeps_jobs_that_match_any_search():
    criteria = SearchCriteria(searches=(SENIOR, CLIMATE))
    jobs = [
        labelled("1", seniority=Seniority.MID),
        labelled("2", seniority=Seniority.MID, domain="x"),
    ]
    assert [j.id for j in MatchStep(criteria, MATCHER).run(jobs)] == ["demo:1"]


@pytest.mark.parametrize(
    ("title", "job_type"),
    [
        ("Senior Data Engineer", "engineering"),
        ("Frontend Developer", "engineering"),
        ("Engineering Manager, Data", "engineering-management"),
        ("Product Designer", "product"),
        ("Grants Coordinator", None),
    ],
)
def test_the_demo_classifier_reads_job_types_from_titles(title, job_type):
    [found] = TitleClassifier().classify([job("1", title)]).values()
    assert found.job_type == job_type
