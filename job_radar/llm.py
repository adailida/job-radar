"""Language models, behind one small interface."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Llm(Protocol):
    """Any language model: one prompt in, one answer out. Stateless."""

    def complete(self, system: str, prompt: str) -> str:
        """Send one prompt and return the model's answer."""
        ...


class ClaudeCli:
    """Claude through the `claude -p` command, on the user's subscription.

    Stateless: holds only the model name.
    """

    def __init__(self, model: str) -> None:
        """Keep the model to ask."""
        self._model = model

    def complete(self, system: str, prompt: str) -> str:
        """Run `claude -p` with the prompt and return its answer."""
        # TODO(task 7): verify the flags; run the command with a timeout.
        raise NotImplementedError
