import pytest

from job_radar.utils.prompter import TerminalPrompter


def prompter(*answers: str) -> tuple[TerminalPrompter, list[str]]:
    """A terminal prompter that reads the given answers and records what it writes."""
    lines: list[str] = []
    replies = iter(answers)

    def read(prompt: str) -> str:
        lines.append(prompt)
        return next(replies)

    return TerminalPrompter(read=read, write=lines.append), lines


@pytest.mark.parametrize("answer", ["", "y", "Y", "yes", " YES "])
def test_enter_and_yes_mean_yes(answer):
    assert prompter(answer)[0].confirm("Continue?") is True


@pytest.mark.parametrize("answer", ["n", "N", "no"])
def test_no_means_no(answer):
    assert prompter(answer)[0].confirm("Continue?") is False


def test_question_shows_lowercase_choices():
    ask, lines = prompter("y")
    ask.confirm("Continue?")
    assert lines == ["Continue? (y/n, Enter for y) "]


def test_other_answers_ask_again():
    ask, lines = prompter("maybe", "n")
    assert ask.confirm("Continue?") is False
    assert lines[1] == "Please answer y or n."


def test_no_input_to_read_takes_the_default():
    def closed(prompt: str) -> str:
        raise EOFError

    assert TerminalPrompter(read=closed, write=print).confirm("Continue?") is True


def test_a_no_default_shows_it_and_enter_means_no():
    ask, lines = prompter("")
    assert ask.confirm("Delete?", default=False) is False
    assert lines == ["Delete? (y/n, Enter for n) "]


def test_no_input_to_read_takes_a_no_default():
    def closed(prompt: str) -> str:
        raise EOFError

    assert TerminalPrompter(read=closed, write=print).confirm("Delete?", default=False) is False
