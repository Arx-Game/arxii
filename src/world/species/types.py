"""Type declarations for the species app (#2993 language web surface)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.species.models import Language


@dataclass(frozen=True)
class MyLanguageRow:
    """One row of the requester's active character's known-languages list.

    Computed (not a single model instance) — joins ``Language`` with the
    character's ``CharacterTraitValue`` fluency and ``CharacterSheet.current_language``
    — so it's a dataclass rather than a queryset row, per the "no dict-to-serializer"
    convention (``django_notes.md``).

    ``fluency``/``band`` are TRAINED (``fluency_value``'s read) — the speak gate, the
    speaker's own band, teaching and self-study. ``effective_fluency``/``effective_band``
    are the LISTENER read (``comprehension_values``): trained plus active-condition
    bonuses (#4090). ``temporary_sources`` names the conditions contributing to that
    bonus, empty when none; a row with no trained value and no positive bonus is omitted.
    """

    language_id: int
    name: str
    fluency: int
    band: str
    is_current: bool
    effective_fluency: int
    effective_band: str
    temporary_sources: tuple[str, ...]


@dataclass(frozen=True)
class ConditionFluencyBonus:
    """Active conditions' summed fluency bonus toward one language, and their names (#4090)."""

    language_id: int
    total: int
    sources: tuple[str, ...]


@dataclass(frozen=True)
class LanguageBreakthroughProspect:
    """A language parked one below an authored XP lock, with its cost (#4090)."""

    language: Language
    next_rating: int
    xp_cost: int
