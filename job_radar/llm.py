"""Language models, behind one small interface."""

import json
import subprocess
import tempfile
from collections.abc import Callable
from typing import Protocol, runtime_checkable


class LlmError(Exception):
    """The model gave no answer: not installed, not logged in, timed out, or failed."""


@runtime_checkable
class Llm(Protocol):
    """Any language model: one prompt in, one answer out. Stateless."""

    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str:
        """Send one prompt and return the model's answer.

        With a JSON schema, the answer is JSON in that shape, as far as the
        model can enforce it; the caller still checks what it needs.
        """
        ...


class ClaudeCli:
    """Claude through the `claude -p` command, on the user's subscription.

    Each call is one turn with no tools, no saved session, no MCP servers and
    no settings, run from an empty folder so no CLAUDE.md is read: a plain
    completion. Stateless: holds only the model, the time limit and how to run
    a command.
    """

    COMMAND = "claude"

    def __init__(
        self,
        model: str,
        timeout: float = 120.0,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        """Keep the model to ask, the seconds to wait per call, and how to run a command."""
        self._model = model
        self._timeout = timeout
        self._run = run

    def check(self) -> None:
        """Fail now if `claude` is missing or not logged in, before anything else runs.

        Asks `claude auth status`, which uses none of the subscription.
        """
        done = self._call([self.COMMAND, "auth", "status"], prompt="")
        try:
            logged_in = json.loads(done.stdout).get("loggedIn") is True
        except (json.JSONDecodeError, AttributeError):
            logged_in = False
        if not logged_in:
            raise LlmError(f"`{self.COMMAND}` is not logged in: run `{self.COMMAND} auth login`")

    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str:
        """Run `claude -p` with the prompt on stdin and return its answer."""
        args = [
            self.COMMAND,
            "-p",
            "--model",
            self._model,
            "--output-format",
            "json",
            "--tools",
            "",
            "--system-prompt",
            system,
            "--no-session-persistence",
            "--strict-mcp-config",
            "--setting-sources",
            "",
        ]
        if schema is not None:
            args += ["--json-schema", json.dumps(schema)]
        done = self._call(args, prompt)
        return self._answer(done, structured=schema is not None)

    def _call(self, args: list[str], prompt: str) -> subprocess.CompletedProcess:
        """Run the command from an empty folder, with the prompt on stdin and a time limit."""
        with tempfile.TemporaryDirectory() as empty:
            try:
                return self._run(
                    args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    cwd=empty,
                )
            except FileNotFoundError:
                raise LlmError(f"`{self.COMMAND}` is not installed: install Claude Code") from None
            except subprocess.TimeoutExpired:
                raise LlmError(f"no answer from `{self.COMMAND}` in {self._timeout:g}s") from None

    def _answer(self, done: subprocess.CompletedProcess, structured: bool) -> str:
        """The answer from the command's JSON output, or an error saying why there is none.

        With a schema, the parsed answer is in `structured_output`; when it is
        missing, the plain text answer comes back for the caller to check.
        """
        try:
            output = json.loads(done.stdout)
        except json.JSONDecodeError:
            detail = (done.stderr or done.stdout).strip()[:300]
            raise LlmError(f"`{self.COMMAND}` failed (exit {done.returncode}): {detail}") from None
        if output.get("is_error") or done.returncode != 0:
            detail = str(output.get("result") or output.get("subtype") or "unknown error")
            raise LlmError(f"`{self.COMMAND}` failed: {detail[:300]}")
        if structured and output.get("structured_output") is not None:
            return json.dumps(output["structured_output"])
        return output.get("result") or ""
