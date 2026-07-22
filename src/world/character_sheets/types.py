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
    worship: IdNameRef | None


class FormTraitEntry(TypedDict):
    """A single form trait (e.g. hair color, eye color) from the TRUE form."""

    trait: str
    value: str


class AppearanceSection(TypedDict):
    """The appearance section of the character sheet API response.

    ``height_inches`` is the exact height, exposed only to the owner / staff (#1325);
    every other observer sees ``None`` there and reads the coarse ``height_band`` label
    instead, so two faces of one character can't be correlated by an identical height.
    ``description`` (the free-text ``additional_desc``) is blank unless the presented
    identity is revealed — a mask must not leak identifying prose.
    """

    height_inches: int | None
    height_band: str | None
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
    at_boundary: bool
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
    # Whether this distinction has been relocated into a Secret (#1334). Non-owners never receive
    # secret entries at all — they're shown the public list only; the flag lets the owner / staff
    # see which of their distinctions are currently gated.
    is_secret: bool
    # Whether this distinction was born from the character's Glimpse (#2427) —
    # CharacterDistinction.from_glimpse is set. Drives the own-character sheet's
    # Glimpse editor "linked distinction" chip state (id here is the
    # CharacterDistinction pk, matching the aura endpoints' character_distinction_id).
    is_from_glimpse: bool


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
    """A resonance within a character's motif, with assigned facets and bound styles."""

    name: str
    facets: list[str]
    styles: list[str]


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


class GlimpseTagEntry(TypedDict):
    """One chosen glimpse tag on the character sheet (#2427)."""

    id: int
    axis: str
    name: str
    description: str


class AuraData(TypedDict):
    """Full aura data including glimpse story (used in magic section)."""

    id: int
    celestial: Decimal
    primal: Decimal
    abyssal: Decimal
    glimpse_story: str
    glimpse_state: str
    glimpse_tags: list[GlimpseTagEntry]
    can_finish_glimpse: bool


class AuraThemingData(TypedDict):
    """Aura percentages for frontend styling (no glimpse story)."""

    celestial: Decimal
    primal: Decimal
    abyssal: Decimal


class ResonanceBalanceEntry(TypedDict):
    """A claimed resonance with its spendable balance and lifetime-earned total (#2032)."""

    name: str
    balance: int
    lifetime_earned: int


class MagicSection(TypedDict):
    """The magic section of the character sheet API response."""

    gifts: list[GiftEntry]
    motif: MotifSection | None
    anima_ritual: AnimaRitualSection | None
    aura: AuraData | None
    resonances: list[ResonanceBalanceEntry]


class StorySection(TypedDict):
    """The story section of the character sheet API response."""

    background: str
    personality: str
    origin_story_state: str
    origin_slots: list[OriginSlotEntry]


class OriginSlotEntry(TypedDict):
    """A character's origin-story slot answer (#2478)."""

    slot_id: int
    slot_name: str
    slot_prompt: str
    value: str


class GoalEntry(TypedDict):
    """A single goal held by the character."""

    domain: str
    points: int
    notes: str


class PersonaEntry(TypedDict):
    """A single persona (character identity) for the character."""

    id: int
    name: str
    thumbnail: str | None


class ThemingSection(TypedDict):
    """The theming section with aura data for frontend styling."""

    aura: AuraThemingData | None


class ProfileTextField(models.TextChoices):
    """Profile prose fields covered by table update requests + version history (#2631).

    Values are Profile attribute names — services setattr() by this value, so a
    new member must match its Profile field name exactly.
    """

    BACKGROUND = "background", "Background"
    PERSONALITY = "personality", "Personality"


class MaritalStatus(models.TextChoices):
    """Marital status choices for characters."""

    SINGLE = "single", "Single"
    MARRIED = "married", "Married"
    WIDOWED = "widowed", "Widowed"
    DIVORCED = "divorced", "Divorced"


class SheetVisibility(models.TextChoices):
    """Player-controlled visibility tier for a character-sheet section (#1271).

    Ordered openness: SELF (owner + staff only) → FRIENDS (also the owner's allow list) →
    PUBLIC (anyone). A viewer sees a section when their access level meets its tier.
    """

    SELF = "self", "Self & staff only"
    FRIENDS = "friends", "Friends / allow list"
    PUBLIC = "public", "Public"


# Openness rank for SheetVisibility — higher = more open. A viewer with access >= the
# section's required rank may see it. Kept here so the model default and the serializer
# resolver agree (#1271).
SHEET_VISIBILITY_RANK: dict[str, int] = {
    SheetVisibility.SELF: 2,
    SheetVisibility.FRIENDS: 1,
    SheetVisibility.PUBLIC: 0,
}


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
