import io

from job_radar.utils.terminal import Terminal

CLEAR = Terminal.CLEAR


def terminal(read=None, width=80) -> tuple[Terminal, io.StringIO]:
    """A terminal over a string, with a fixed width and a set way to read answers."""
    out = io.StringIO()
    return Terminal(out, tty=True, read=read or (lambda prompt: ""), width=lambda: width), out


def test_without_a_live_line_it_prints_plain_lines():
    shown, out = terminal()
    shown.write("hello")
    assert out.getvalue() == "hello\n"


def test_a_live_line_is_drawn_in_place_and_replaced():
    shown, out = terminal()
    shown.live("[1/3] fetch  1 of 5")
    shown.live("[1/3] fetch  2 of 5")
    assert out.getvalue() == (f"{CLEAR}[1/3] fetch  1 of 5{CLEAR}{CLEAR}[1/3] fetch  2 of 5")


def test_a_live_line_is_cut_to_the_width_so_it_cannot_wrap():
    shown, out = terminal(width=10)
    shown.live("x" * 40)
    assert out.getvalue() == f"{CLEAR}" + "x" * 9


def test_settling_replaces_the_live_line_with_a_line_that_stays():
    shown, out = terminal()
    shown.live("working")
    shown.settle("done")
    assert out.getvalue() == f"{CLEAR}working{CLEAR}done\n"
    shown.write("later")
    assert out.getvalue().endswith("done\nlater\n")  # no live line comes back


def test_a_message_clears_the_live_line_and_the_line_is_drawn_again_after():
    shown, out = terminal()
    shown.live("working")
    shown.write("a warning")
    assert out.getvalue() == f"{CLEAR}working{CLEAR}a warning\n{CLEAR}working"


def test_a_question_clears_the_live_line_while_it_waits_and_draws_it_again():
    seen = []
    shown, out = terminal(read=lambda prompt: seen.append((prompt, out.getvalue())) or "y")
    shown.live("working")
    assert shown.read("Keep going? ") == "y"
    prompt, before = seen[0]
    assert prompt == "Keep going? "
    assert before == f"{CLEAR}working{CLEAR}"  # cleared before the question is shown
    assert out.getvalue().endswith(f"{CLEAR}working")


def test_a_question_that_reads_nothing_still_draws_the_live_line_again():
    def closed(prompt):
        raise EOFError

    shown, out = terminal(read=closed)
    shown.live("working")
    try:
        shown.read("Continue? ")
    except EOFError:
        pass
    assert out.getvalue().endswith(f"{CLEAR}working")


def test_it_knows_whether_the_output_is_a_terminal():
    assert Terminal(io.StringIO()).tty is False
    assert Terminal(io.StringIO(), tty=True).tty is True
