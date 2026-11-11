import json
import re
from datetime import date

from fakes import FakePrompter, MemoryWarningLog, guard, job

from job_radar.llm.extractor import KeywordExtractor, LlmExtractor
from job_radar.models import Extraction, Job, Requirement, RequirementType, Window
from job_radar.pipeline.steps.extract import ExtractStep
from job_radar.storage.checkpoints import FileCheckpoints

PYTHON = {"type": "tool", "name": "Python", "years": None}


def answer(*ids: str, requirements=(PYTHON,)) -> str:
    """A model answer giving these ids the same requirements."""
    return json.dumps({"jobs": [{"id": i, "requirements": list(requirements)} for i in ids]})


class ReadingLlm:
    """A model that answers for every id in the prompt, or gives set answers first."""

    def __init__(self, *answers: str):
        self._answers = list(answers)
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if self._answers:
            return self._answers.pop(0)
        return answer(*re.findall(r'<job id="(j\d+)">', prompt))


def extractor(llm, batch_size=10, chars=30) -> LlmExtractor:
    """The extractor over this model."""
    return LlmExtractor(llm, batch_size, chars)


def described(source_id: str, text: str = "We use Python.") -> Job:
    """A job with a description."""
    one = job(source_id)
    posting = one.postings[0].model_copy(update={"description": text})
    return one.model_copy(update={"postings": (posting,)})


def test_reads_each_jobs_requirements_by_its_id():
    years = {"type": "years", "name": " software   engineering ", "years": 5}
    llm = ReadingLlm(answer("j1", requirements=(PYTHON, years)))
    found = extractor(llm).extract([described("1")])
    assert found == {
        "demo:1": Extraction(
            job_id="demo:1",
            requirements=(
                Requirement(type=RequirementType.TOOL, name="Python"),
                Requirement(type=RequirementType.YEARS, name="software engineering", years=5),
            ),
            prompt_version="extract-1",
        )
    }


def test_names_are_tidied_and_repeats_and_stray_years_dropped():
    repeated = (
        {"type": "tool", "name": "Python", "years": 3},
        {"type": "tool", "name": "python", "years": None},
        {"type": "skill", "name": "  ", "years": None},
    )
    llm = ReadingLlm(answer("j1", requirements=repeated))
    [found] = extractor(llm).extract([described("1")]).values()
    assert found.requirements == (Requirement(type=RequirementType.TOOL, name="Python"),)


def test_the_prompt_cuts_long_descriptions_and_holds_to_the_schema():
    llm = ReadingLlm()
    extractor(llm, chars=30).extract([described("1", "B" * 50)])
    assert "B" * 30 + " [cut]" in llm.prompts[0] and "B" * 31 not in llm.prompts[0]
    item = llm.schemas[0]["properties"]["jobs"]["items"]["properties"]["requirements"]["items"]
    assert item["properties"]["type"]["enum"] == ["skill", "tool", "certification", "years"]


def test_a_bad_answer_is_asked_again_then_the_batch_is_split():
    llm = ReadingLlm(answer("j1"), answer("j1"))
    found = extractor(llm).extract([described("1"), described("2")])
    assert set(found) == {"demo:1", "demo:2"}
    assert "Your last answer could not be used: missing: j2" in llm.prompts[1]
    assert len(llm.prompts) == 4


def test_a_job_that_keeps_failing_gets_no_extraction():
    assert extractor(ReadingLlm("not json", "not json")).extract([described("1")]) == {}


def test_jobs_go_a_set_number_to_a_prompt():
    llm = ReadingLlm()
    extractor(llm, batch_size=2).extract([described(str(n)) for n in range(5)])
    assert [len(re.findall("<job id", p)) for p in llm.prompts] == [2, 2, 1]


def test_the_demo_extractor_finds_known_names_and_years():
    text = "Build data pipelines in Python and SQL. 5+ years of experience. AWSOME team."
    [found] = KeywordExtractor().extract([described("1", text)]).values()
    assert [(r.type.value, r.name, r.years) for r in found.requirements] == [
        ("tool", "Python", None),
        ("tool", "SQL", None),
        ("skill", "data pipelines", None),
        ("years", "experience", 5),
    ]


class SetExtractions:
    """An extractor with set results by job id."""

    def __init__(self, found: dict):
        self._found = found

    def extract(self, jobs):
        return self._found


def test_the_step_adds_requirements_and_says_how_many_failed():
    extraction = Extraction(job_id="demo:1", requirements=(), prompt_version="test")
    prompter, warnings = FakePrompter(), MemoryWarningLog()
    step = ExtractStep(SetExtractions({"demo:1": extraction}), prompter, guard(), warnings)
    found = step.run([job("1"), job("2")])
    assert [j.extraction for j in found] == [extraction, None]
    said = (
        "The LLM couldn't read the requirements of 1 of 2 jobs: "
        "they are left out of What employers ask for."
    )
    assert prompter.told == [said]
    assert warnings.messages() == [said]


def test_no_jobs_asks_nothing():
    llm = ReadingLlm()
    assert ExtractStep(extractor(llm), FakePrompter(), guard(), MemoryWarningLog()).run([]) == []
    assert llm.prompts == []


def test_a_completed_run_keeps_the_extracted_jobs(tmp_path):
    window = Window(start=date(2026, 11, 8), end=date(2026, 11, 9))
    checkpoints = FileCheckpoints(tmp_path, window, keep={ExtractStep.name: "jobs.jsonl"})
    extraction = Extraction(job_id="demo:1", requirements=(), prompt_version="test")
    checkpoints.save("match", [job("1")])
    checkpoints.save("extract", [job("1").model_copy(update={"extraction": extraction})])
    checkpoints.complete()
    [kept] = [Job.model_validate_json(line) for line in (tmp_path / "jobs.jsonl").open()]
    assert kept.extraction == extraction
