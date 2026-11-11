from datetime import date

from fakes import job

from job_radar.models import DropList, DroppedJob, Window
from job_radar.report.words import Words
from job_radar.storage.drop_log import FileDropLog

WINDOW = Window(start=date(2026, 10, 26), end=date(2026, 11, 9))


def drops(*dropped: DroppedJob, before_window: int = 0) -> DropList:
    """A drop list for the window, with 20 jobs checked and 2 kept."""
    return DropList(window=WINDOW, checked=20, kept=2, before_window=before_window, dropped=dropped)


def dropped(title: str, *reasons: str) -> DroppedJob:
    """A job with this title, dropped for these reasons."""
    return DroppedJob(job=job(title.lower().replace(" ", "-"), title), reasons=reasons)


def test_groups_dropped_jobs_by_reason_largest_first_titles_sorted(tmp_path):
    text = FileDropLog(tmp_path, Words()).render(
        drops(
            dropped("Rust Engineer", "remote-us: work mode", "seattle: location"),
            dropped("Grants Coordinator", "remote-us: roles", "seattle: roles"),
            dropped("analyst", "remote-us: roles", "seattle: roles"),
            before_window=5,
        )
    )
    assert text == (
        "# Dropped by the filter, 9 Nov 2026\n"
        "\n"
        "Covers postings from 26 Oct to 9 Nov 2026. 20 jobs checked, 2 kept, 3 dropped by the "
        "searches. 5 posted before the window aren't listed.\n"
        "\n"
        "## remote-us: roles; seattle: roles (2)\n"
        "\n"
        "- analyst, Example Org (Remote.)\n"
        "- Grants Coordinator, Example Org (Remote.)\n"
        "\n"
        "## remote-us: work mode; seattle: location (1)\n"
        "\n"
        "- Rust Engineer, Example Org (Remote.)\n"
    )


def test_says_when_nothing_was_dropped(tmp_path):
    text = FileDropLog(tmp_path, Words()).render(drops())
    assert text.endswith("0 dropped by the searches.\n\nNothing was dropped.\n")


def test_writes_dropped_md_in_the_run_folder(tmp_path):
    FileDropLog(tmp_path, Words()).write(drops(dropped("Designer", "default: roles")))
    assert "- Designer, Example Org" in (tmp_path / "dropped.md").read_text()
