"""What the LLM gives: a job's labels and requirements, and how each compares with the CV."""

from enum import StrEnum

from job_radar.models.model import Model


class Seniority(StrEnum):
    """Level of a role, as judged from the posting."""

    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"  # staff, principal, tech lead
    MANAGER = "manager"
    EXECUTIVE = "executive"  # director and above
    UNKNOWN = "unknown"


class RequirementType(StrEnum):
    """Kind of thing a posting asks for."""

    SKILL = "skill"
    TOOL = "tool"
    CERTIFICATION = "certification"
    YEARS = "years"


class Classification(Model):
    """Labels for one job, used to match it against searches and group it in the report."""

    job_id: str
    seniority: Seniority
    job_type: str | None = None  # a job type from settings, "Other", or None when unclear
    domain: str | None = None  # a domain from settings, "Other", or None when unclear
    sector: str | None = None  # free label, for an informational breakdown
    prompt_version: str  # prompt that produced the labels


class Requirement(Model):
    """One thing a posting asks for: a skill, tool, certification or years of experience."""

    type: RequirementType
    name: str  # normalized: "Python", "CISSP"
    years: int | None = None  # for type years: 5 in "5+ years of Python"


class Extraction(Model):
    """The requirements found in one matched job's posting."""

    job_id: str
    requirements: tuple[Requirement, ...]
    prompt_version: str  # prompt that produced the requirements


class GapStatus(StrEnum):
    """How far the CV shows a requirement."""

    COVERED = "covered"
    PARTLY = "partly"  # some of it, such as fewer years than asked or a related tool
    MISSING = "missing"


class GapJudgment(Model):
    """How one requirement compares with the CV, and how to gain it when it's a gap."""

    status: GapStatus
    reason: str  # one line
    suggestion: str | None = None  # how to gain it; only for some gaps
    prompt_version: str
