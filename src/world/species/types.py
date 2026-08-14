"""Type declarations for the species app (#2993 language web surface)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MyLanguageRow:
    """One row of the requester's active character's known-languages list.

    Computed (not a single model instance) — joins ``Language`` with the
    character's ``CharacterTraitValue`` fluency and ``CharacterSheet.current_language``
    — so it's a dataclass rather than a queryset row, per the "no dict-to-serializer"
    convention (``django_notes.md``).
    """

    language_id: int
    name: str
    fluency: int
    band: str
    is_current: bool
