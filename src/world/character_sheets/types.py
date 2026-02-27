"""
Type definitions for character sheets app.
"""

from __future__ import annotations

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

    celestial: int
    primal: int
    abyssal: int
    glimpse_story: str


class AuraThemingData(TypedDict):
    """Aura percentages for frontend styling (no glimpse story)."""

    celestial: int
    primal: int
    abyssal: int


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


class GuiseEntry(TypedDict):
    """A single guise (disguise identity) for the character."""

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
