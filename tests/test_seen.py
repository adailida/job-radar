from datetime import date, timedelta

from fakes import MemoryWarningLog, job

from job_radar.models import Job, Window
from job_radar.pipeline.steps.new_jobs_filter import NewJobsFilterStep
from job_radar.storage.checkpoints import FileCheckpoints
from job_radar.storage.run_history import FileRunHistory
from job_radar.storage.seen_jobs import FileSeenJobs

TODAY = date(2026, 11, 9)
ATS = "greenhouse:acme:42"
FUZZY = "acme|data engineer|US"


def keyed(source_id: str, *keys: str) -> Job:
    """A job with these identity keys, then its posting's own key."""
    one = job(source_id)
    return one.model_copy(update={"keys": (*keys, one.postings[0].key)})


def run(runs, name: str, end: date, jobs: list[Job], completed: bool = True) -> None:
    """A run folder that ended on that day, having kept these jobs."""
    folder = runs / name
    folder.mkdir(parents=True)
    checkpoints = FileCheckpoints(
        folder, Window(start=end - timedelta(days=1), end=end), keep={"filter": "jobs.jsonl"}
    )
    checkpoints.save("filter", jobs)
    if completed:
        checkpoints.complete()


def seen(runs) -> frozenset[str]:
    """The keys that mark a job as seen today."""
    warnings = MemoryWarningLog()
    return FileSeenJobs(FileRunHistory(runs, warnings), runs, warnings).keys(TODAY)


def test_a_completed_runs_kept_jobs_are_seen(tmp_path):
    run(tmp_path, "2026-11-08T09-00-00", date(2026, 11, 8), [keyed("1", ATS, FUZZY)])
    assert seen(tmp_path) == {ATS, FUZZY, "demo:1"}


def test_a_failed_runs_jobs_are_not_seen(tmp_path):
    run(tmp_path, "2026-11-08T09-00-00", date(2026, 11, 8), [keyed("1", ATS)], completed=False)
    assert seen(tmp_path) == frozenset()


def test_fuzzy_keys_count_for_60_days_strong_keys_for_good(tmp_path):
    old = TODAY - timedelta(days=61)
    run(tmp_path, "2026-09-09T09-00-00", old, [keyed("1", ATS, FUZZY)])
    assert seen(tmp_path) == {ATS, "demo:1"}


def test_a_run_with_no_kept_jobs_or_an_unreadable_file_adds_nothing(tmp_path):
    run(tmp_path, "2026-11-07T09-00-00", date(2026, 11, 7), [])
    run(tmp_path, "2026-11-08T09-00-00", date(2026, 11, 8), [keyed("1", ATS)])
    (tmp_path / "2026-11-08T09-00-00" / "jobs.jsonl").write_text('{"id": "x"}\n')
    assert seen(tmp_path) == frozenset()


class SetKeys:
    """Seen jobs with a set of keys."""

    def __init__(self, *keys: str):
        self._keys = frozenset(keys)

    def keys(self, today: date) -> frozenset[str]:
        return self._keys


def test_the_step_drops_jobs_with_any_seen_key():
    jobs = [keyed("1", ATS), keyed("2", FUZZY), keyed("3", "other|title|US")]
    kept = NewJobsFilterStep(SetKeys(FUZZY, "demo:1"), TODAY, new_only=True).run(jobs)
    assert [j.id for j in kept] == ["demo:3"]


def test_with_new_only_off_every_job_passes():
    jobs = [keyed("1", ATS), keyed("2", FUZZY)]
    assert NewJobsFilterStep(SetKeys(ATS, FUZZY), TODAY, new_only=False).run(jobs) == jobs
