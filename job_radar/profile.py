"""The user's CV and preferences, read from their local files."""

from pathlib import Path

from job_radar.model import CandidateProfile

DEMO_PROFILE = CandidateProfile(
    cv=(
        "Backend engineer with eight years of Python. Built data pipelines, APIs and "
        "platform tooling for small teams. Senior engineer on my last two teams."
    ),
    preferences=(
        "A senior data or platform role at a mission-driven organisation. Remote or hybrid."
    ),
)
"""A made-up profile for `job-radar run --demo` and the end-to-end tests."""


class ProfileLoader:
    """Reads the CV and preferences from the user's local folder into a profile.

    Stateless: holds only the folder.
    """

    def __init__(self, folder: Path) -> None:
        """Keep the folder with `cv.pdf` and `preferences.md`."""
        self._folder = folder

    def load(self) -> CandidateProfile:
        """Read the CV text and the preferences into a profile."""
        # TODO(task 7b): read cv.pdf and preferences.md; fail clearly if missing.
        raise NotImplementedError
