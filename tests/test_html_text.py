from job_radar.html_text import HtmlText


def text(html: str) -> str:
    return HtmlText().text(html)


def test_paragraphs_become_blocks_with_one_blank_line_between():
    assert text("<p>First.</p><p>Second.</p>") == "First.\n\nSecond."


def test_headings_and_divs_are_paragraphs_too():
    assert text("<h3>About</h3><div>We build things.</div>") == "About\n\nWe build things."


def test_a_line_break_starts_a_new_line():
    assert text("<p><strong>Team:</strong> Data<br><strong>Location:</strong> Remote</p>") == (
        "Team: Data\nLocation: Remote"
    )


def test_list_items_become_dash_lines_on_consecutive_lines():
    html = "<p>You will:</p><ul><li>Build pipelines</li><li><p>Mentor others</p></li></ul>"
    assert text(html) == "You will:\n- Build pipelines\n- Mentor others"


def test_inline_tags_are_dropped_and_their_text_kept():
    html = '<p>Read <a href="https://example.org">our <em>values</em></a>.</p>'
    assert text(html) == "Read our values."


def test_entities_are_decoded():
    assert text("<p>R&amp;D &lt;3 caf&eacute;&nbsp;team</p>") == "R&D <3 café team"


def test_source_whitespace_collapses_as_a_browser_shows_it():
    assert text("<p>  Senior\n   Data\tEngineer  </p>\n\n\n<p>Next</p>") == (
        "Senior Data Engineer\n\nNext"
    )


def test_scripts_and_styles_are_left_out():
    html = "<style>p { color: red }</style><p>Visible</p><script>track()</script>"
    assert text(html) == "Visible"


def test_plain_text_passes_through_and_empty_stays_empty():
    assert text("Just words.") == "Just words."
    assert text("") == ""
