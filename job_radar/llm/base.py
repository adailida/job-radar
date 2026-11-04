"""The interface to a language model."""

from typing import Protocol


class LLM(Protocol):
    """A language model the run sends prompts to: text in, text out.

    Turning replies into structured data happens outside, in one shared helper,
    so a new way of calling a model only has to implement `complete`.

    Stateless: each call stands alone; no conversation is kept between calls.
    """

    def complete(self, system: str, prompt: str) -> str:
        """Send one prompt with its system instructions and return the model's reply."""
        ...
