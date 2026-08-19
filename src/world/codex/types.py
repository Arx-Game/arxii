"""Typed value objects for the codex app."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterKnowledge:
    """One character's knowledge of one codex entry, for API display.

    Built by the codex viewsets from ``CharacterCodexKnowledge`` rows scoped
    to the requesting account's characters, and consumed by the entry
    serializers to render per-character knowledge (the ``known_by`` field)
    without further queries.
    """

    roster_entry_id: int
    character_name: str
    status: str
    learning_progress: int
