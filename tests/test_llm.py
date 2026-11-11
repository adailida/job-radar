import json
import subprocess
from pathlib import Path

import pytest

from job_radar.llm.llm import ClaudeCli, LlmError


class Runner:
    """A fake command runner: records each call and gives a set result, or raises."""

    def __init__(self, stdout: str = "", returncode: int = 0, error: Exception | None = None):
        self._stdout = stdout
        self._returncode = returncode
        self._error = error
        self.calls: list[dict] = []

    def __call__(self, args, **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(
            {"args": args, **kwargs, "cwd_files": list(Path(kwargs["cwd"]).iterdir())}
        )
        if self._error:
            raise self._error
        return subprocess.CompletedProcess(args, self._returncode, self._stdout, "")


def result(**fields) -> str:
    """The JSON `claude -p --output-format json` prints, with the given fields."""
    return json.dumps({"type": "result", "subtype": "success", "is_error": False} | fields)


def test_complete_runs_one_plain_turn_with_the_prompt_on_stdin():
    runner = Runner(result(result="pong"))
    assert ClaudeCli("haiku", timeout=30, run=runner).complete("Be brief.", "ping") == "pong"
    [call] = runner.calls
    args = call["args"]
    assert args[:2] == ["claude", "-p"]
    assert args[args.index("--model") + 1] == "haiku"
    assert args[args.index("--system-prompt") + 1] == "Be brief."
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--setting-sources") + 1] == ""
    assert {"--no-session-persistence", "--strict-mcp-config"} <= set(args)
    assert "--json-schema" not in args
    assert (call["input"], call["timeout"]) == ("ping", 30)


def test_complete_runs_from_an_empty_folder_so_no_claude_md_is_read():
    runner = Runner(result(result="pong"))
    ClaudeCli("haiku", run=runner).complete("s", "p")
    [call] = runner.calls
    assert call["cwd_files"] == []
    assert not Path(call["cwd"]).exists()  # removed after the call


def test_complete_with_a_schema_gives_the_structured_answer_as_json():
    schema = {"type": "object"}
    runner = Runner(result(result="ignored", structured_output={"scores": []}))
    answer = ClaudeCli("haiku", run=runner).complete("s", "p", schema)
    assert json.loads(answer) == {"scores": []}
    args = runner.calls[0]["args"]
    assert json.loads(args[args.index("--json-schema") + 1]) == schema


def test_complete_with_a_schema_but_no_structured_answer_gives_the_text():
    runner = Runner(result(result="not json"))
    assert ClaudeCli("haiku", run=runner).complete("s", "p", {"type": "object"}) == "not json"


def test_an_error_result_fails_with_its_message():
    runner = Runner(result(is_error=True, result="Usage limit reached"), returncode=1)
    with pytest.raises(LlmError, match="Usage limit reached"):
        ClaudeCli("haiku", run=runner).complete("s", "p")


def test_output_that_isnt_json_fails():
    with pytest.raises(LlmError, match="exit 1"):
        ClaudeCli("haiku", run=Runner("boom", returncode=1)).complete("s", "p")


def test_a_timeout_fails():
    runner = Runner(error=subprocess.TimeoutExpired("claude", 120))
    with pytest.raises(LlmError, match="no answer from `claude` in 120s"):
        ClaudeCli("haiku", run=runner).complete("s", "p")


def test_claude_not_installed_fails():
    runner = Runner(error=FileNotFoundError("claude"))
    with pytest.raises(LlmError, match="not installed"):
        ClaudeCli("haiku", run=runner).complete("s", "p")


def test_check_passes_when_logged_in():
    runner = Runner(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
    ClaudeCli("haiku", run=runner).check()
    assert runner.calls[0]["args"] == ["claude", "auth", "status"]


@pytest.mark.parametrize("stdout", [json.dumps({"loggedIn": False}), "", "[]"])
def test_check_fails_when_not_logged_in(stdout):
    with pytest.raises(LlmError, match="not logged in"):
        ClaudeCli("haiku", run=Runner(stdout, returncode=1)).check()


def test_check_fails_when_claude_is_not_installed():
    with pytest.raises(LlmError, match="not installed"):
        ClaudeCli("haiku", run=Runner(error=FileNotFoundError("claude"))).check()


@pytest.mark.live
def test_live_claude_answers_with_the_schema():
    """Opt-in: `uv run pytest -m live`. One short call on the subscription."""
    schema = {
        "type": "object",
        "properties": {"word": {"type": "string"}},
        "required": ["word"],
    }
    llm = ClaudeCli("haiku")
    llm.check()
    answer = llm.complete("You answer in one word.", "Say the word pong.", schema)
    assert json.loads(answer)["word"].strip(".").lower() == "pong"
