from io import BytesIO

import pytest
from pypdf import PdfWriter

from job_radar.profile import ProfileError, ProfileLoader


def text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with the lines as real text, built by hand so the test sets every byte."""
    text = " ".join(f"({line}) Tj 0 -20 Td" for line in lines)
    stream = f"BT /F1 12 Tf 72 720 Td {text} ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def blank_pdf() -> bytes:
    """A PDF page with no text, like a scanned CV."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def with_preferences(folder, text="A remote data role."):
    (folder / "preferences.md").write_text(text)
    return folder


def test_reads_a_pdf_cv_and_the_preferences(tmp_path):
    (with_preferences(tmp_path) / "cv.pdf").write_bytes(text_pdf(["Jane Example", "Data engineer"]))
    profile = ProfileLoader(tmp_path).load()
    assert "Jane Example" in profile.cv and "Data engineer" in profile.cv
    assert profile.preferences == "A remote data role."


@pytest.mark.parametrize("name", ["cv.md", "cv.txt"])
def test_reads_a_markdown_or_text_cv(tmp_path, name):
    (with_preferences(tmp_path) / name).write_text("# Jane Example\n\nData engineer.\n")
    assert ProfileLoader(tmp_path).load().cv == "# Jane Example\n\nData engineer."


def test_a_pdf_cv_comes_before_the_others(tmp_path):
    (with_preferences(tmp_path) / "cv.md").write_text("From Markdown")
    (tmp_path / "cv.pdf").write_bytes(text_pdf(["From PDF"]))
    assert ProfileLoader(tmp_path).load().cv == "From PDF"


def test_missing_cv_is_a_setup_error(tmp_path):
    with pytest.raises(ProfileError, match="no CV in .*: add one of cv.pdf, cv.md, cv.txt"):
        ProfileLoader(with_preferences(tmp_path)).load()


def test_a_scanned_pdf_with_no_text_is_a_setup_error(tmp_path):
    (with_preferences(tmp_path) / "cv.pdf").write_bytes(blank_pdf())
    with pytest.raises(ProfileError, match="has no text .*scanned PDF"):
        ProfileLoader(tmp_path).load()


def test_a_file_that_isnt_a_pdf_is_a_setup_error(tmp_path):
    (with_preferences(tmp_path) / "cv.pdf").write_bytes(b"not a pdf")
    with pytest.raises(ProfileError, match="can't be read as a PDF"):
        ProfileLoader(tmp_path).load()


def test_an_empty_cv_is_a_setup_error(tmp_path):
    (with_preferences(tmp_path) / "cv.md").write_text("  \n")
    with pytest.raises(ProfileError, match="has no text"):
        ProfileLoader(tmp_path).load()


def test_missing_preferences_is_a_setup_error(tmp_path):
    (tmp_path / "cv.md").write_text("Jane")
    with pytest.raises(ProfileError, match="no .*preferences.md: describe your ideal job"):
        ProfileLoader(tmp_path).load()


def test_empty_preferences_is_a_setup_error(tmp_path):
    (with_preferences(tmp_path, "\n") / "cv.md").write_text("Jane")
    with pytest.raises(ProfileError, match="preferences.md is empty"):
        ProfileLoader(tmp_path).load()
