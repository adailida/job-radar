from datetime import date

from fakes import FakePrompter, posting

from job_radar.model import Job
from job_radar.steps.describe import DescribeStep


class FakeDescriber:
    """A board's describer that answers from a set of texts and records what it was asked."""

    def __init__(self, source: str, texts: dict[str, str], pace: float = 1.0):
        """Keep the board name, the text for each posting id, and the pace to report."""
        self.source = source
        self.pace = pace
        self._texts = texts
        self.asked: list[str] = []

    def describe(self, p) -> str:
        """The set text for the posting."""
        self.asked.append(p.source_id)
        return self._texts[p.source_id]


def job_of(*postings) -> Job:
    """A job made of the given postings, the first one primary."""
    keys = tuple(p.key for p in postings)
    return Job(id=keys[0], keys=keys, postings=postings, first_seen=date(2026, 11, 5))


def test_fills_in_the_primary_postings_description():
    getro = FakeDescriber("getro", {"1": "Build pipelines."})
    other = posting("9", source="getro")
    job = job_of(posting("1", source="getro"), other)
    [described] = DescribeStep({"getro": getro}, FakePrompter()).run([job])
    assert described.postings[0].description == "Build pipelines."
    assert described.postings[1] == other  # one request per job, for the primary only
    assert getro.asked == ["1"]
    assert (described.id, described.keys) == (job.id, job.keys)


def test_a_posting_that_has_a_description_passes_through():
    getro = FakeDescriber("getro", {})
    job = job_of(posting("1", source="getro").model_copy(update={"description": "Already."}))
    assert DescribeStep({"getro": getro}, FakePrompter()).run([job]) == [job]
    assert getro.asked == []


def test_a_board_without_a_describer_passes_through():
    job = job_of(posting("1", source="demo"))
    prompter = FakePrompter()
    assert DescribeStep({}, prompter).run([job]) == [job]
    assert prompter.told == []


def test_keeps_the_order_of_the_jobs():
    getro = FakeDescriber("getro", {"1": "One.", "3": "Three."})
    jobs = [
        job_of(posting(i, source=s)) for i, s in [("1", "getro"), ("2", "demo"), ("3", "getro")]
    ]
    described = DescribeStep({"getro": getro}, FakePrompter()).run(jobs)
    assert [j.postings[0].source_id for j in described] == ["1", "2", "3"]
    assert getro.asked == ["1", "3"]


def test_says_how_long_it_will_take_before_it_starts():
    getro = FakeDescriber("getro", {str(i): "" for i in range(150)})
    prompter = FakePrompter()
    DescribeStep({"getro": getro}, prompter).run(
        [job_of(posting(str(i), source="getro")) for i in range(150)]
    )
    assert prompter.told == ["Fetching full descriptions for 150 jobs: about 2 min."]


def test_a_short_wait_says_under_a_minute():
    getro = FakeDescriber("getro", {"1": ""})
    prompter = FakePrompter()
    DescribeStep({"getro": getro}, prompter).run([job_of(posting("1", source="getro"))])
    assert prompter.told == ["Fetching full descriptions for 1 job: under a minute."]
