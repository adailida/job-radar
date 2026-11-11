"""The base every domain model builds on."""

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Base for all domain models: immutable, and rejects fields it doesn't know.

    Rejecting unknown fields means a typo in saved data fails loudly on load
    instead of being silently dropped.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
