from fakes import job

from job_radar.checkpoints import FileCheckpoints
from job_radar.model import Job, StepCount


def test_saved_items_load_back(tmp_path):
    checkpoints = FileCheckpoints(tmp_path)
    jobs = [job("1"), job("2", "Analyst")]
    checkpoints.save("dedupe", jobs)
    assert checkpoints.load("dedupe", Job) == jobs


def test_empty_output_saves_and_counts_zero(tmp_path):
    checkpoints = FileCheckpoints(tmp_path)
    checkpoints.save("filter", [])
    assert checkpoints.load("filter", Job) == []
    assert checkpoints.funnel() == [StepCount(step="filter", count=0)]


def test_has_only_saved_steps(tmp_path):
    checkpoints = FileCheckpoints(tmp_path)
    assert not checkpoints.has("dedupe")
    checkpoints.save("dedupe", [job("1")])
    assert checkpoints.has("dedupe")
    assert not checkpoints.has("filter")


def test_funnel_counts_per_step_in_order(tmp_path):
    checkpoints = FileCheckpoints(tmp_path)
    checkpoints.save("dedupe", [job("1"), job("2")])
    checkpoints.save("filter", [job("1")])
    assert checkpoints.funnel() == [
        StepCount(step="dedupe", count=2),
        StepCount(step="filter", count=1),
    ]


def test_saving_a_step_again_replaces_its_count(tmp_path):
    checkpoints = FileCheckpoints(tmp_path)
    checkpoints.save("dedupe", [job("1"), job("2")])
    checkpoints.save("dedupe", [job("1")])
    assert checkpoints.funnel() == [StepCount(step="dedupe", count=1)]


def test_discard_all_keeps_manifest_and_report(tmp_path):
    checkpoints = FileCheckpoints(tmp_path)
    checkpoints.save("dedupe", [job("1")])
    checkpoints.save("filter", [job("1")])
    (tmp_path / "report.md").write_text("# report\n")
    checkpoints.discard_all()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json", "report.md"]
    assert len(checkpoints.funnel()) == 2


def test_no_temp_files_left(tmp_path):
    FileCheckpoints(tmp_path).save("dedupe", [job("1")])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dedupe.jsonl", "manifest.json"]
