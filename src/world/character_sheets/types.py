"""
Type definitions for character sheets app.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from django.db import models

# --- API response shape TypedDicts ---


class IdNameRef(TypedDict):
    """A minimal {id, name} reference to a related model instance."""

    id: int
    name: str


class PronounsData(TypedDict):
    """Pronoun set for a character."""

    subject: str
    object: str
    possessive: str


class IdentitySection(TypedDict):
    """The identity section of the character sheet API response."""

    name: str
    fullname: str
    concept: str
    quote: str
    age: int | None
    gender: IdNameRef | None
    pronouns: PronounsData
    species: IdNameRef | None
    heritage: IdNameRef | None
    family: IdNameRef | None
    tarot_card: IdNameRef | None
    origin: IdNameRef | None
    path: IdNameRef | None


class FormTraitEntry(TypedDict):
    """A single form trait (e.g. hair color, eye color) from the TRUE form."""

    trait: str
    value: str


class AppearanceSection(TypedDict):
    """The appearance section of the character sheet API response."""

    height_inches: int | None
    build: IdNameRef | None
    description: str
    form_traits: list[FormTraitEntry]


class SkillRef(TypedDict):
    """Reference to a skill with its category."""

    id: int
    name: str
    category: str


class SpecializationEntry(TypedDict):
    """A single specialization within a skill."""

    id: int
    name: str
    value: int


class SkillEntry(TypedDict):
    """A skill with its value and nested specializations."""

    skill: SkillRef
    value: int
    specializations: list[SpecializationEntry]


class PathHistoryEntry(TypedDict):
    """A single entry in the character's path progression history."""

    path: str
    stage: int
    tier: str
    date: str


class PathDetailSection(TypedDict):
    """The detailed path section of the character sheet API response."""

    id: int
    name: str
    stage: int
    tier: str
    history: list[PathHistoryEntry]


class DistinctionEntry(TypedDict):
    """A single distinction held by the character."""

    id: int
    name: str
    rank: int
    notes: str


class TechniqueEntry(TypedDict):
    """A single magic technique within a gift."""

    name: str
    level: int
    style: str
    description: str


class GiftEntry(TypedDict):
    """A magic gift with its resonances and techniques."""

    name: str
    description: str
    resonances: list[str]
    techniques: list[TechniqueEntry]


class MotifResonanceEntry(TypedDict):
    """A resonance within a character's motif, with assigned facets."""

    name: str
    facets: list[str]


class MotifSection(TypedDict):
    """The motif sub-section of magic."""

    description: str
    resonances: list[MotifResonanceEntry]


class AnimaRitualSection(TypedDict):
    """The anima ritual sub-section of magic."""

    stat: str
    skill: str
    resonance: str
    description: str


class AuraData(TypedDict):
    """Full aura data including glimpse story (used in magic section)."""

    celestial: Decimal
    primal: Decimal
    abyssal: Decimal
    glimpse_story: str


class AuraThemingData(TypedDict):
    """Aura percentages for frontend styling (no glimpse story)."""

    celestial: Decimal
    primal: Decimal
    abyssal: Decimal


class MagicSection(TypedDict):
    """The magic section of the character sheet API response."""

    gifts: list[GiftEntry]
    motif: MotifSection | None
    anima_ritual: AnimaRitualSection | None
    aura: AuraData | None


class StorySection(TypedDict):
    """The story section of the character sheet API response."""

    background: str
    personality: str


class GoalEntry(TypedDict):
    """A single goal held by the character."""

    domain: str
    points: int
    notes: str


class PersonaEntry(TypedDict):
    """A single persona (character identity) for the character."""

    id: int
    name: str
    description: str
    thumbnail: str | None


class ThemingSection(TypedDict):
    """The theming section with aura data for frontend styling."""

    aura: AuraThemingData | None


class MaritalStatus(models.TextChoices):
    """Marital status choices for characters."""

    SINGLE = "single", "Single"
    MARRIED = "married", "Married"
    WIDOWED = "widowed", "Widowed"
    DIVORCED = "divorced", "Divorced"


class Gender(models.TextChoices):
    """Gender choices for characters."""

    MALE = "male", "Male"
    FEMALE = "female", "Female"
    NON_BINARY = "non_binary", "Non-Binary"
    OTHER = "other", "Other"


class ActivityState(models.TextChoices):
    """OOC engagement state for a CharacterSheet (#671).

    Orthogonal to LifecycleState. Consumer systems treat any non-ACTIVE state
    as "Dormant" via CharacterSheet.is_dormant.
    """

    ACTIVE = "ACTIVE", "Active"
    HIATUS = "HIATUS", "Hiatus (player-declared)"
    INACTIVE = "INACTIVE", "Inactive (auto-inferred)"
    FROZEN = "FROZEN", "Frozen (OC swap, time-bounded)"


class LifecycleState(models.TextChoices):
    """IC condition for a CharacterSheet (#671).

    Orthogonal to ActivityState. Consumer systems treat any non-ALIVE state
    as "Dormant" via CharacterSheet.is_dormant.
    """

    ALIVE = "ALIVE", "Alive"
    CAPTURED = "CAPTURED", "Captured / Unknown"
    COMA = "COMA", "Coma"
    RETIRED = "RETIRED", "Retired"
    DEAD = "DEAD", "Dead"


class DecayTier(models.TextChoices):
    """Graduated inactivity vocabulary returned by CharacterSheet.decay_tier (#671).

    Computed from days-since-last-signal. Returned as a TextChoices value (string)
    so consumers can ``if sheet.decay_tier == DecayTier.LONG_INACTIVE`` without
    string-typo risk. Returns None when the character is still within the
    RECENT_INACTIVE-or-better window.
    """

    RECENT_INACTIVE = "RECENT_INACTIVE", "Recently inactive (14+ days)"
    INACTIVE = "INACTIVE", "Inactive (30+ days)"
    LONG_INACTIVE = "LONG_INACTIVE", "Long inactive (90+ days)"
    DORMANT = "DORMANT", "Dormant (365+ days)"


DECAY_TIER_THRESHOLDS_DAYS = {
    DecayTier.DORMANT: 365,
    DecayTier.LONG_INACTIVE: 90,
    DecayTier.INACTIVE: 30,
    DecayTier.RECENT_INACTIVE: 14,
}
"""Tier → minimum days-since-signal. Walked in descending-threshold order so the
biggest matching tier wins. Tuneable; the values match the #671 spec."""
