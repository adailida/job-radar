from job_radar.models import SourceCount
from job_radar.storage.source_count_log import FileSourceCountLog


def test_the_count_log_keeps_the_last_counts_written(tmp_path):
    log = FileSourceCountLog(tmp_path)
    log.write([SourceCount(source="getro", postings=3)])
    log.write([SourceCount(source="getro", postings=200), SourceCount(source="demo", postings=0)])
    assert log.counts() == [
        SourceCount(source="getro", postings=200),
        SourceCount(source="demo", postings=0),
    ]
    assert (tmp_path / "source_counts.jsonl").is_file()


def test_no_counts_recorded_means_none(tmp_path):
    assert FileSourceCountLog(tmp_path / "none").counts() == []
