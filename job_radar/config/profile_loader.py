"""The user's CV and preferences, read from their local files."""

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from job_radar.models import CandidateProfile
from job_radar.utils.errors import SetupError

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


class ProfileError(SetupError):
    """The CV or preferences can't be read: missing, empty, or a PDF with no text."""


class ProfileLoader:
    """Reads the CV and preferences from the user's local folder into a profile.

    The CV is `cv.pdf`, `cv.md` or `cv.txt`, the first found in that order; a
    PDF is read locally, so only its text goes anywhere. The preferences are
    `preferences.md`, the ideal job in the user's own words. Stateless: holds
    only the folder.
    """

    CV_NAMES = ("cv.pdf", "cv.md", "cv.txt")
    PREFERENCES = "preferences.md"

    def __init__(self, folder: Path) -> None:
        """Keep the folder with the CV and `preferences.md`."""
        self._folder = folder

    def load(self) -> CandidateProfile:
        """Read the CV text and the preferences into a profile, or say what's missing."""
        return CandidateProfile(cv=self._cv(), preferences=self._preferences())

    def _cv(self) -> str:
        """The CV's text, from the first CV file found."""
        found = [self._folder / name for name in self.CV_NAMES if (self._folder / name).is_file()]
        if not found:
            names = ", ".join(self.CV_NAMES)
            raise ProfileError(f"no CV in {self._folder}/: add one of {names}")
        path = found[0]
        text = self._pdf_text(path) if path.suffix == ".pdf" else path.read_text(encoding="utf-8")
        if not text.strip():
            hint = (
                " (a scanned PDF? Export a text PDF, or use cv.md)" if path.suffix == ".pdf" else ""
            )
            raise ProfileError(f"{path} has no text{hint}")
        return text.strip()

    def _pdf_text(self, path: Path) -> str:
        """The text of every page of a PDF, a blank line between pages."""
        try:
            pages = PdfReader(path).pages
        except PdfReadError as error:
            raise ProfileError(f"{path} can't be read as a PDF: {error}") from None
        return "\n\n".join((page.extract_text() or "").strip() for page in pages)

    def _preferences(self) -> str:
        """The preferences, in the user's own words."""
        path = self._folder / self.PREFERENCES
        if not path.is_file():
            raise ProfileError(f"no {path}: describe your ideal job there, in your own words")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ProfileError(f"{path} is empty: describe your ideal job there")
        return text
