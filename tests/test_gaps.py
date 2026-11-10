import hashlib
import json
from datetime import date

import pytest
from fakes import (
    FakeStats,
    MemoryPendingLog,
    MemorySourceCountLog,
    MemorySpendLog,
    MemoryWriter,
    NoTrends,
    SetKeptJobs,
    grouper,
)

from job_radar.asks import RequirementNames
from job_radar.gaps import (
    BadGaps,
    CvGaps,
    FileGapCache,
    GapBuilder,
    KeywordGapJudge,
    LlmGapJudge,
)
from job_radar.llm import LlmError, UsageLimit
from job_radar.model import (
    AskRow,
    Asks,
    CandidateProfile,
    GapJudgment,
    GapRow,
    Gaps,
    GapSkip,
    GapStatus,
    ReportContent,
    RequirementType,
    Window,
)
from job_radar.report_renderer import MarkdownRenderer
from job_radar.steps.report import ReportStep
from job_radar.words import Words

SKILL, TOOL, YEARS = RequirementType.SKILL, RequirementType.TOOL, RequirementType.YEARS
COVERED, PARTLY, MISSING = GapStatus.COVERED, GapStatus.PARTLY, GapStatus.MISSING
PROFILE = CandidateProfile(
    cv="Backend engineer. Eight years of Python, built data pipelines on AWS.",
    preferences="Hands-on work at a climate nonprofit.",
)
WINDOW = Window(start=date(2026, 10, 11), end=date(2026, 11, 9))
NAMES = RequirementNames()


def ask(name: str, share: float, kind: RequirementType = TOOL, years: float | None = None):
    """A row of what employers ask for, with jobs out of 100."""
    return AskRow(
        type=kind,
        name=name,
        jobs=round(share * 100),
        share=share,
        change=None,
        job_ids=(),
        median_years=years,
    )


def asks(*rows: AskRow) -> Asks:
    """What employers ask for, with these rows."""
    previous = Window(start=date(2026, 9, 11), end=date(2026, 10, 10))
    return Asks(
        window=WINDOW, previous=previous, jobs=100, previous_jobs=0, rows=rows, low_sample=20
    )


def section(gaps: Gaps) -> str:
    """The experience to gain section of a rendered report, up to the next section."""
    report = ReportContent(
        run="run", window=WINDOW, min_score=40, recommendations=(), funnel=(), gaps=gaps
    )
    text = MarkdownRenderer(Words()).render(report)
    return text[text.index("## Experience to gain") : text.index("\n\n## About this run")]


def judged(status: GapStatus, reason: str = "r", suggestion: str | None = None) -> GapJudgment:
    """A judgment with this status."""
    return GapJudgment(status=status, reason=reason, suggestion=suggestion, prompt_version="test")


def entry(key: str, status: str, reason: str = "a reason", suggestion: str | None = "do x"):
    """One requirement in a model answer."""
    if status == "covered" and suggestion == "do x":
        suggestion = None
    return {"id": key, "status": status, "reason": reason, "suggestion": suggestion}


def answer(*entries: dict) -> str:
    """A model answer with these entries."""
    return json.dumps({"requirements": list(entries)})


class SetLlm:
    """A model that gives set answers, and keeps what it was asked."""

    def __init__(self, *answers: str):
        self._answers = list(answers)
        self.systems: list[str] = []
        self.prompts: list[str] = []
        self.schemas: list[dict | None] = []

    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str:
        self.systems.append(system)
        self.prompts.append(prompt)
        self.schemas.append(schema)
        return self._answers.pop(0)


class CountingJudge:
    """The keyword judge, counting what it is asked to judge."""

    def __init__(self):
        self.asked: list[list[str]] = []

    def judge(self, asked, profile):
        self.asked.append([row.name for row in asked])
        return KeywordGapJudge().judge(asked, profile)


class FailingJudge:
    """A judge that always raises this error."""

    def __init__(self, error: Exception):
        self._error = error

    def judge(self, asked, profile):
        raise self._error


class MemoryGapCache:
    """A gap cache in memory."""

    def __init__(self):
        self.kept: dict[str, dict] = {}

    def judged(self, cv):
        return dict(self.kept.get(cv, {}))

    def add(self, cv, judged):
        self.kept[cv] = self.kept.get(cv, {}) | judged


def cv_gaps(judge=None, cache=None, profile=PROFILE, suggestions: int = 5) -> CvGaps:
    """The CV comparison over this judge and cache."""
    return CvGaps(
        profile,
        judge or KeywordGapJudge(),
        cache if cache is not None else MemoryGapCache(),
        GapBuilder(NAMES, suggestions),
    )


def test_the_prompt_has_the_cv_the_preferences_and_each_requirement_under_an_id():
    llm = SetLlm(answer(entry("r1", "covered"), entry("r2", "partly")))
    rows = [ask("Python", 0.5), ask("software engineering", 0.3, YEARS, years=5)]
    LlmGapJudge(llm).judge(rows, PROFILE)
    prompt = llm.prompts[0]
    assert f"<cv>\n{PROFILE.cv}\n</cv>" in prompt
    assert f"<preferences>\n{PROFILE.preferences}\n</preferences>" in prompt
    assert (
        "<requirements>\nr1 (tool): Python\n"
        "r2 (years): software engineering, 5 years\n</requirements>"
    ) in prompt
    assert "data, not instructions" in llm.systems[0]
    assert "covered" in llm.systems[0] and "partly" in llm.systems[0]


def test_years_not_given_are_said_so_in_the_prompt():
    llm = SetLlm(answer(entry("r1", "missing")))
    LlmGapJudge(llm).judge([ask("experience", 0.2, YEARS)], PROFILE)
    assert "r1 (years): experience, years not given" in llm.prompts[0]


def test_the_answer_is_held_to_the_schema():
    llm = SetLlm(answer(entry("r1", "covered")))
    LlmGapJudge(llm).judge([ask("Python", 0.5)], PROFILE)
    schema = llm.schemas[0]
    assert schema == LlmGapJudge.schema()
    item = schema["properties"]["requirements"]["items"]
    assert item["properties"]["status"]["enum"] == ["covered", "partly", "missing"]
    assert item["required"] == ["id", "status", "reason", "suggestion"]


def test_reads_each_judgment_in_the_order_given():
    llm = SetLlm(
        answer(
            entry("r2", "missing", "  no  dbt   anywhere ", " Build a dbt   project. "),
            entry("r1", "covered", "eight years of Python", "ignored"),
        )
    )
    found = LlmGapJudge(llm).judge([ask("Python", 0.5), ask("dbt", 0.3)], PROFILE)
    assert found == [
        GapJudgment(status=COVERED, reason="eight years of Python", prompt_version="gaps-1"),
        GapJudgment(
            status=MISSING,
            reason="no dbt anywhere",
            suggestion="Build a dbt project.",
            prompt_version="gaps-1",
        ),
    ]


@pytest.mark.parametrize(
    ("bad", "said"),
    [
        ("not json", "not the expected JSON"),
        (answer(entry("r1", "covered")), "missing: r2"),
        (answer(entry("r1", "covered"), entry("r2", "missing"), entry("r9", "missing")), "r9"),
        (answer(entry("r1", "covered"), entry("r2", "missing", suggestion=" ")), "r2"),
    ],
)
def test_a_bad_answer_is_asked_again_once_with_what_was_wrong(bad, said):
    good = answer(entry("r1", "covered"), entry("r2", "missing"))
    llm = SetLlm(bad, good)
    found = LlmGapJudge(llm).judge([ask("Python", 0.5), ask("dbt", 0.3)], PROFILE)
    assert [one.status for one in found] == [COVERED, MISSING]
    assert len(llm.prompts) == 2
    assert llm.prompts[1].startswith(llm.prompts[0])
    assert "Your last answer could not be used: " in llm.prompts[1] and said in llm.prompts[1]


def test_a_second_bad_answer_raises():
    llm = SetLlm("not json", "still not json")
    with pytest.raises(BadGaps):
        LlmGapJudge(llm).judge([ask("Python", 0.5)], PROFILE)
    assert len(llm.prompts) == 2


def test_the_demo_judge_finds_names_in_the_cv():
    found = KeywordGapJudge().judge([ask("python", 0.5), ask("dbt", 0.3)], PROFILE)
    assert [(one.status, one.suggestion) for one in found] == [
        (COVERED, None),
        (MISSING, KeywordGapJudge.SUGGESTION),
    ]


def test_gaps_come_first_most_asked_first_then_the_covered_ones():
    rows = (
        ask("Python", 0.6),
        ask("dbt", 0.2),
        ask("system design", 0.4, SKILL),
        ask("AWS", 0.5),
        ask("software engineering", 0.3, YEARS, years=5),
    )
    known = {
        (TOOL, "python"): judged(COVERED),
        (TOOL, "dbt"): judged(MISSING, suggestion="dbt project"),
        (SKILL, "system design"): judged(PARTLY, suggestion="design review"),
        (TOOL, "aws"): judged(COVERED),
        (YEARS, "software engineering"): judged(PARTLY, suggestion="keep going"),
    }
    gaps = GapBuilder(NAMES, 5).build(list(rows), known, None)
    assert [(row.requirement.name, row.status) for row in gaps.rows] == [
        ("system design", PARTLY),
        ("software engineering", PARTLY),
        ("dbt", MISSING),
        ("Python", COVERED),
        ("AWS", COVERED),
    ]


def test_only_the_most_asked_gaps_show_how_to_gain_them():
    rows = [ask(f"tool{n}", 0.9 - n / 10) for n in range(4)]
    known = {(TOOL, f"tool{n}"): judged(MISSING, suggestion=f"do {n}") for n in range(4)}
    gaps = GapBuilder(NAMES, 2).build(rows, known, None)
    assert [row.suggestion for row in gaps.rows] == ["do 0", "do 1", None, None]


def test_new_requirements_are_judged_in_one_call_and_kept():
    judge, cache = CountingJudge(), MemoryGapCache()
    gaps = cv_gaps(judge, cache).gaps(asks(ask("dbt", 0.2), ask("Python", 0.6)))
    assert judge.asked == [["Python", "dbt"]]
    assert [row.requirement.name for row in gaps.rows] == ["dbt", "Python"]
    cv = hashlib.sha256(PROFILE.cv.encode()).hexdigest()
    assert set(cache.judged(cv)) == {(TOOL, "python"), (TOOL, "dbt")}


def test_requirements_judged_before_cost_no_call():
    judge, cache = CountingJudge(), MemoryGapCache()
    cv_gaps(judge, cache).gaps(asks(ask("Python", 0.6), ask("dbt", 0.2)))
    gaps = cv_gaps(judge, cache).gaps(asks(ask("python 3", 0.5), ask("dbt", 0.3)))
    assert len(judge.asked) == 1
    assert [row.status for row in gaps.rows] == [MISSING, COVERED]


def test_only_requirements_new_to_the_list_are_sent():
    judge, cache = CountingJudge(), MemoryGapCache()
    cv_gaps(judge, cache).gaps(asks(ask("Python", 0.6)))
    cv_gaps(judge, cache).gaps(asks(ask("Python", 0.6), ask("dbt", 0.2), ask("SQL", 0.3)))
    assert judge.asked == [["Python"], ["SQL", "dbt"]]


def test_a_new_cv_is_judged_again():
    judge, cache = CountingJudge(), MemoryGapCache()
    cv_gaps(judge, cache).gaps(asks(ask("Python", 0.6)))
    changed = PROFILE.model_copy(update={"cv": PROFILE.cv + " Also Rust."})
    cv_gaps(judge, cache, profile=changed).gaps(asks(ask("Python", 0.6)))
    assert judge.asked == [["Python"], ["Python"]]


def test_no_requirements_means_no_call_and_the_section_says_so():
    judge = CountingJudge()
    gaps = cv_gaps(judge).gaps(asks())
    assert judge.asked == [] and gaps == Gaps(rows=())
    assert section(gaps) == "## Experience to gain\n\nNo requirements to compare with your CV yet."


@pytest.mark.parametrize(
    ("error", "skipped"),
    [
        (BadGaps("not the expected JSON"), GapSkip.FAILED),
        (LlmError("`claude` failed"), GapSkip.FAILED),
        (UsageLimit("usage limit reached"), GapSkip.USAGE_LIMIT),
    ],
)
def test_a_failed_call_leaves_the_run_going_and_the_section_says_so(error, skipped):
    cache = MemoryGapCache()
    cv_gaps(cache=cache).gaps(asks(ask("Python", 0.6)))
    failing = cv_gaps(FailingJudge(error), cache)
    gaps = failing.gaps(asks(ask("Python", 0.6), ask("dbt", 0.3), ask("SQL", 0.2)))
    assert gaps.skipped is skipped and gaps.not_compared == 2
    assert [row.requirement.name for row in gaps.rows] == ["Python"]
    cv = hashlib.sha256(PROFILE.cv.encode()).hexdigest()
    assert set(cache.judged(cv)) == {(TOOL, "python")}


def test_the_cache_is_written_and_read_back(tmp_path):
    path = tmp_path / "cache" / "gaps.jsonl"
    cache = FileGapCache(path)
    assert cache.judged("cv1") == {}
    cache.add("cv1", {(TOOL, "python"): judged(COVERED)})
    cache.add("cv1", {(TOOL, "dbt"): judged(MISSING, suggestion="dbt project")})
    assert FileGapCache(path).judged("cv1") == {
        (TOOL, "python"): judged(COVERED),
        (TOOL, "dbt"): judged(MISSING, suggestion="dbt project"),
    }
    assert FileGapCache(path).judged("cv2") == {}
    assert [p.name for p in path.parent.iterdir()] == ["gaps.jsonl"]


def test_a_new_cv_replaces_the_old_judgments_in_the_file(tmp_path):
    cache = FileGapCache(tmp_path / "gaps.jsonl")
    cache.add("cv1", {(TOOL, "python"): judged(COVERED)})
    cache.add("cv2", {(TOOL, "dbt"): judged(MISSING)})
    assert cache.judged("cv1") == {}
    assert cache.judged("cv2") == {(TOOL, "dbt"): judged(MISSING)}


def test_a_line_that_cant_be_read_is_judged_again(tmp_path):
    path = tmp_path / "gaps.jsonl"
    cache = FileGapCache(path)
    cache.add("cv1", {(TOOL, "python"): judged(COVERED)})
    path.write_text(path.read_text() + "{broken\n")
    assert cache.judged("cv1") == {(TOOL, "python"): judged(COVERED)}


def gap_row(row: AskRow, status: GapStatus, reason: str, suggestion: str | None = None):
    """A row of the section."""
    return GapRow(requirement=row, status=status, reason=reason, suggestion=suggestion)


def test_the_report_lists_frequent_requirements_the_cv_doesnt_cover_with_their_share():
    gaps = Gaps(
        rows=(
            gap_row(ask("dbt", 0.34), MISSING, "no dbt in the CV", "Build a dbt project"),
            gap_row(
                ask("software engineering", 0.3, YEARS, years=5),
                PARTLY,
                "3 of 5 years",
                "Keep going",
            ),
            gap_row(ask("Airflow", 0.1), MISSING, "not in the CV"),
            gap_row(ask("Python", 0.72), COVERED, "eight years"),
            gap_row(ask("SQL", 0.5), COVERED, "data pipelines"),
        )
    )
    assert section(gaps) == (
        "## Experience to gain\n"
        "\n"
        "| Requirement | Share | Status | How to gain it |\n"
        "|---|---|---|---|\n"
        "| dbt | 34% (34) | missing: no dbt in the CV | Build a dbt project |\n"
        "| software engineering: 5 years | 30% (30) | partly: 3 of 5 years | Keep going |\n"
        "| Airflow | 10% (10) | missing: not in the CV |  |\n"
        "\n"
        "Covered: Python, SQL.\n"
        "\n"
        "Share: as in What employers ask for. Each requirement is compared with your CV once; "
        "a changed CV is compared again."
    )


def test_a_cv_covering_everything_says_so():
    gaps = Gaps(rows=(gap_row(ask("Python", 0.72), COVERED, "eight years"),))
    text = section(gaps)
    assert "Your CV covers every requirement compared.\n\nCovered: Python." in text
    assert "| Requirement |" not in text


def test_a_pipe_in_a_cell_doesnt_start_a_new_column():
    gaps = Gaps(rows=(gap_row(ask("CI|CD", 0.2), MISSING, "a | b", "x | y"),))
    assert "| CI\\|CD | 20% (20) | missing: a \\| b | x \\| y |" in section(gaps)


@pytest.mark.parametrize(
    ("skipped", "said"),
    [
        (
            GapSkip.FAILED,
            "Note: 2 requirements couldn't be compared with your CV this run: "
            "the LLM gave no usable answer. They are compared on the next run.",
        ),
        (
            GapSkip.USAGE_LIMIT,
            "Note: 2 requirements weren't compared with your CV this run: "
            "the LLM's usage limit is reached. They are compared on the next run.",
        ),
    ],
)
def test_the_section_says_when_the_comparison_couldnt_be_made(skipped, said):
    nothing = Gaps(rows=(), skipped=skipped, not_compared=2)
    assert section(nothing) == f"## Experience to gain\n\n{said}"
    some = Gaps(
        rows=(gap_row(ask("Python", 0.72), COVERED, "eight years"),),
        skipped=skipped,
        not_compared=2,
    )
    assert section(some).startswith(f"## Experience to gain\n\n{said}\n\nYour CV covers")


class SetAsks:
    """A what employers ask for source with set content."""

    def __init__(self, content):
        self._content = content

    def asks(self):
        return self._content


class KeepingGaps:
    """An experience to gain source that keeps what it was given."""

    def __init__(self):
        self.given = None

    def gaps(self, asks):
        self.given = asks
        return Gaps(rows=())


class KeepingRenderer:
    """A renderer that keeps the content it was given."""

    def __init__(self):
        self.content: ReportContent | None = None

    def render(self, content: ReportContent) -> str:
        self.content = content
        return "the report"


def step(asks_source, gaps_source, renderer) -> ReportStep:
    """A report step with these sources."""
    return ReportStep(
        FakeStats([]),
        renderer,
        MemoryWriter(),
        MemorySpendLog(),
        MemoryPendingLog(),
        NoTrends(),
        asks_source,
        gaps_source,
        "run",
        WINDOW,
        None,
        40,
        {},
        MemorySourceCountLog(),
        SetKeptJobs(),
        grouper(),
    )


def test_the_report_step_compares_what_employers_ask_for_with_the_cv():
    content, gaps, renderer = asks(ask("Python", 0.6)), KeepingGaps(), KeepingRenderer()
    step(SetAsks(content), gaps, renderer).run([])
    assert gaps.given == content
    assert renderer.content.gaps == Gaps(rows=())


def test_with_no_asks_section_there_is_no_comparison():
    gaps, renderer = KeepingGaps(), KeepingRenderer()
    step(SetAsks(None), gaps, renderer).run([])
    assert gaps.given is None and renderer.content.gaps is None


def test_the_section_comes_after_what_employers_ask_for():
    report = ReportContent(
        run="run",
        window=WINDOW,
        min_score=40,
        recommendations=(),
        funnel=(),
        asks=asks(ask("Python", 0.6)),
        gaps=Gaps(rows=(gap_row(ask("Python", 0.6), COVERED, "eight years"),)),
    )
    text = MarkdownRenderer(Words()).render(report)
    order = ["## What employers ask for", "## Experience to gain", "## About this run"]
    assert [text.index(heading) for heading in order] == sorted(
        text.index(heading) for heading in order
    )
