"""LLM interface (design section 9). JSON parsing lives in a shared helper, not here."""

from typing import Protocol


class LLM(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...
