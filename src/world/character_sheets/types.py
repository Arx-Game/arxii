"""
Type definitions for character sheets app.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from django.db import models

from world.magic.types.technique_effects import (
    TechniqueEffectPayload,
    TechniqueFormPayload,
    TechniqueSignaturePayload,
)

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


class VacancyRef(TypedDict):
    """The character's held vacancy, as the identity section presents it (#3648).

    ``importance`` (the family's real reckoning) is owner/staff only, mirroring
    the age-axes leak-table pattern; ``presumed_importance`` (what outsiders
    assume) is always shown.
    """

    name: str
    presumed_importance: int
    importance: int | None


class IdentitySection(TypedDict):
    """The identity section of the character sheet API response."""

    name: str
    fullname: str
    concept: str
    quote: str
    age: int | None
    birthday: str | None
    # Age axes (#2756): populated only for the owner/staff; always None for
    # other viewers (leak table). chronological_age is None for a Sleeper even
    # on their own sheet — unknowable, rendered "Unknown".
    chronological_age: int | None
    biological_age: int | None
    withered_years: int | None
    gender: IdNameRef | None
    pronouns: PronounsData
    species: IdNameRef | None
    heritage: IdNameRef | None
    # #3898 — every Beginnings this character holds (#3775): what the sheet calls their
    # "Beginning". NOT the same as ``origin``, which is the realm they are from.
    beginnings: list[IdNameRef]
    family: IdNameRef | None
    tarot_card: IdNameRef | None
    origin: IdNameRef | None
    path: IdNameRef | None
    worship: IdNameRef | None
    # #2361 — the heart-vs-lip-service inward truth (WorshipDeclaration.public_is_sincere).
    # Owner/staff only, always None for other viewers — the public record shows only
    # the public act (Ratified amendment #2); mirrors the current_mood leak-table pattern.
    worship_sincere: bool | None
    # #2994 — internal declared mood; owner/staff only, always None for other
    # viewers (never rendered to observers, per the spec's inward-only ruling).
    current_mood: IdNameRef | None
    # #3648 - the character's held vacancy, if any active membership carries one.
    vacancy: VacancyRef | None


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
    # #3898/#3739 — the distinctive feature this row is aimed at (a trait row or a
    # marking), by display name; blank for an ordinary distinction. The sheet's Physical
    # page lists the non-blank ones, since a feature is something a person can see.
    feature: str
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
    #: What the technique actually does (#2898) — the same block CG, the magic
    #: API, and the in-scene cast list carry, so the sheet can't drift from them.
    effect_summary: TechniqueEffectPayload
    #: Which forms of it this caster can work (#2901): the base form, each
    #: unlocked resonance-specialized variant, and one step ahead. Always at
    #: least one entry. The sheet describes, so it carries the full catalogue;
    #: the in-scene cast list carries only a compact affordance.
    forms: list[TechniqueFormPayload]
    #: The signature flourish riding whichever form is chosen, or ``None``.
    #: Additive, never a sibling form (ADR-0072), so it sits beside the list.
    signature: TechniqueSignaturePayload | None


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
    origin_story_state: str
    origin_slots: list[OriginSlotEntry]


class OriginSlotEntry(TypedDict):
    """A character's origin-story slot answer (#2478).

    ``kind``/``connection_kind``/``life_stage`` mirror the prompt (#3660); ``choice_name``/
    ``choice_description`` are the picked choice's own fields. ``organization_id``/
    ``organization_name`` are the resolved anchor (a GROUP question's pick, or the group a
    PERSON question's named figure belongs to). ``figure_name`` is blanked for a non-privileged
    viewer (the foreign-viewer redaction; #3660) - it never leaves the owner/staff.
    """

    slot_id: int
    slot_name: str
    slot_prompt: str
    value: str
    kind: str
    connection_kind: str
    life_stage: str
    choice_name: str
    choice_description: str
    organization_id: int | None
    organization_name: str
    figure_name: str


class GoalEntry(TypedDict):
    """A single goal held by the character, numbered within its horizon (#3621)."""

    domain: str
    horizon: str
    ordinal: int
    points: int
    notes: str


class EnemyEntry(TypedDict):
    """The priced enemy row; owner, staff and assigned GM only (#3621)."""

    kind: str
    name: str
    power_tier: str
    reach: str
    degree: str
    price: int
    why: str
    public_line: str
    status: str
    has_secret: bool


class IntroductionEntry(TypedDict):
    """One of the Introductions, a white journal found by its kind (#3621)."""

    id: int
    kind: str
    title: str
    body: str
    created_at: str


class ActorSheetSection(TypedDict):
    """The Actor's Sheet block (#3621): three answers, the enemy's public line, the
    Introductions. ``enemy`` is the full row for a privileged viewer, else None."""

    never_do: str
    protect: str
    fear: str
    enemy_public_line: str
    enemy: EnemyEntry | None
    introductions: list[IntroductionEntry]


class PersonaEntry(TypedDict):
    """A single persona (character identity) for the character."""

    id: int
    name: str
    thumbnail: str | None


class ThemingSection(TypedDict):
    """The theming section with aura data for frontend styling."""

    aura: AuraThemingData | None


class LookEntry(TypedDict):
    """One image of the character, tagged with the mood it shows (#3898).

    The sheet's plate shows the look the character currently wears and offers the
    rest as a strip beside it. ``tenure_media_id`` is the id
    ``POST /api/roster/entries/{pk}/set_profile_picture/`` takes, so the owner can
    make any look the worn one from the sheet itself; ``look`` is the
    ``MoodOption`` name the image was tagged with, blank for an untagged image.
    ``is_current`` marks the roster entry's profile picture — exactly one entry
    carries it when a profile picture is set, none when it is not.
    """

    tenure_media_id: int
    url: str
    title: str
    look: str
    is_current: bool


class OrgDomainEntry(TypedDict):
    """One landholding an organization this character belongs to owns (#3901).

    The discovery line: a player coming onto a roster character may not know their
    house holds a keep, or where it is. A ``Domain`` is org-owned (``owner_org``, the
    #1884/#930 ruling) and a character can never hold one, so this says whose it is
    and where, never that it is theirs.

    ``where`` is the area the domain decorates. Whether the character may walk into it
    is a separate question answered by ``LocationTenancy`` against the land, not by
    this list.
    """

    id: int
    name: str
    organization: str
    where: str


class OrgMembershipEntry(TypedDict):
    """One organization the presented face belongs to, and what it calls them (#3906)."""

    organization_id: int
    organization: str
    title: str


class OrgReputationEntry(TypedDict):
    """What one organization thinks of the presented face (#3906).

    The NAMED TIER only, never the raw value — the standing convention
    ``OrganizationReputationSerializer`` sets and this payload keeps.
    """

    organization_id: int
    organization: str
    tier: str


class StandingSection(TypedDict):
    """Where the character stands with the organizations of the world (#3906).

    Gated by ``CharacterSheet.standing_visibility``, which is the only one of the
    sheet's visibility tiers that defaults to FRIENDS rather than SELF: what a house
    thinks of you is something your friends would know.

    Read off the PRESENTED persona, which makes it mask-safe for free (#1109) — an alt
    face carries its own memberships or none, so a masked character never leaks the
    real one's house through this.
    """

    memberships: list[OrgMembershipEntry]
    reputations: list[OrgReputationEntry]


class CovenantRoleEntry(TypedDict):
    """One active covenant role the character holds (#3906).

    PUBLIC, by Apostate's ruling. The covenant-roles endpoint is self-only, so this
    rides the sheet payload rather than widening that endpoint for every caller.
    """

    id: int
    covenant_id: int
    covenant: str
    role: str
    rank: str
    engaged: bool


class MentorBondEntry(TypedDict):
    """One active Mentor's Vow bond this character holds (#1165), for Ties (#3898).

    ``role`` is what the OTHER party is to this character: the mentor who took them on,
    or the student they took on. The covenant is named because the vow is sworn inside
    one, and a character may hold bonds in more than one.
    """

    id: int
    name: str
    role: str
    covenant: str


class WornEntry(TypedDict):
    """One piece the character has on, for the sheet's Physical section (#3898).

    Worn things are visible things, so this rides the sheet payload rather than the
    equipped-items endpoint. That endpoint answers "what am I wearing" for the player
    who owns the character, and ``VisibleWornItemViewSet`` answers "what can I see on
    them" for someone in the same room; a roster visitor is neither, and the ruling is
    that what a character wears shows on their sheet to anyone who opens it.

    ``is_hidden`` marks a piece the layer walk (#2985) says is covered by something
    above it. Those rows are dropped for everyone but the owner and staff, who get them
    with the flag set so the sheet can say the piece is there and unseen.
    """

    id: int
    name: str
    description: str
    is_hidden: bool


class ProfileTextField(models.TextChoices):
    """Profile prose fields covered by table update requests + version history (#2631).

    Values are Profile attribute names — services setattr() by this value, so a
    new member must match its Profile field name exactly.
    """

    BACKGROUND = "background", "Background"
    NEVER_DO = "never_do", "What would you never do?"
    PROTECT = "protect", "What would you protect at all costs?"
    FEAR = "fear", "What are you deathly afraid of?"


class EnemyKind(models.TextChoices):
    """Who wants the character to fail: one person, or a group (#3621)."""

    PERSON = "person", "A person"
    GROUP = "group", "A group"


class EnemyPowerTier(models.TextChoices):
    """A person's power on the Path ladder, with Quiescent for someone with no Gift (#3621).

    Mirrors ``classes.PathStage`` above Quiescent; kept as its own choice set so an enemy
    who is not a PC needs no Path row.
    """

    QUIESCENT = "quiescent", "Quiescent"
    PROSPECT = "prospect", "Prospect"
    POTENTIAL = "potential", "Potential"
    PUISSANT = "puissant", "Puissant"
    TRUE = "true", "True"
    GRAND = "grand", "Grand"


class EnemyDegree(models.TextChoices):
    """How badly the enemy wants it (#3621). Death is not a tier: ruined includes it."""

    ANNOYED = "annoyed", "They want you annoyed"
    THWARTED = "thwarted", "They want you thwarted"
    RUINED = "ruined", "They want you ruined"
    DESTROY = "destroy", "They will relentlessly try to destroy you"


class EnemyStatus(models.TextChoices):
    """Whether the enemy is linked to a real person or group the world can send (#3621)."""

    PLACED = "placed", "Placed"
    PENDING = "pending", "Pending staff placement"


class PosthumousJournalDisposition(models.TextChoices):
    """Author-controlled default for what happens to private journal entries after death (#3287).

    REVEAL is the default — the Arx I black-journal precedent (a private journal became the
    historical record once its author died). SEAL keeps everything private buried forever. A
    per-entry ``JournalEntry.posthumous_override`` (INHERIT/REVEAL/SEAL) can override this
    default for individual entries; INHERIT falls through to this field.
    """

    REVEAL = "reveal", "Reveal after death (default)"
    SEAL = "seal", "Seal forever"


class PlateInk(models.TextChoices):
    """The ground colour a character's sheet plate is printed in (#3898).

    The sheet reads as the reference sheet an artist makes for a character, and the
    plate behind the art is the one thing about it the player chooses. Four inks
    only: a wide palette would make the roster read as a set of unrelated pages,
    and the page below the plate stays on Arx paper whichever is picked (the CG
    ruling of 2026-09-03 — a realm is an ink, never a different page).

    Picked in account settings rather than on the sheet: the sheet describes the
    character, and its own chrome is never one of the character's fields.
    """

    EMBER = "ember", "Ember"
    VERDIGRIS = "verdigris", "Verdigris"
    ROSE = "rose", "Rose"
    NIGHT = "night", "Night"


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


class ProfileBeginningsSource(models.TextChoices):
    """Why a character holds a Beginnings (#3775).

    ``CHARACTER_CREATION`` is where play began, written by the wizard once per
    character (the partial unique constraint on ``ProfileBeginnings`` enforces
    once). The others are origins a character came to know later, added by staff:
    a Sleeper remembering the homeland they were taken from, a reincarnation
    remembering a former life. The value ``character_creation`` is the spelling
    ``DistinctionOrigin`` and ``AcquisitionOrigin`` already use for the same fact.
    """

    CHARACTER_CREATION = "character_creation", "Where play began"
    RECOVERED_MEMORY = "recovered_memory", "A memory recovered"
    PAST_LIFE = "past_life", "A past life remembered"


class LifecycleState(models.TextChoices):
    """IC condition for a CharacterSheet (#671).

    Orthogonal to ActivityState. Consumer systems treat any non-ALIVE state
    as "Dormant" via CharacterSheet.is_dormant.
    """

    ALIVE = "ALIVE", "Alive"
    CAPTURED = "CAPTURED", "Captured"
    # Split from CAPTURED (#2728 §2). "Captured" means someone is holding them —
    # the captivity system drives it. "Unknown" means their whereabouts are
    # genuinely unknown in-world, which is a mystery investigation can resolve.
    # Smashing the two together made the state unusable for anyone searching.
    UNKNOWN = "UNKNOWN", "Whereabouts unknown"
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
    # Named SHORT_INACTIVE, not INACTIVE (#2728 §3): a bare ``INACTIVE`` here
    # collides with ActivityState.INACTIVE, and the two mean different things —
    # this is a day-count tier, that is the flag a sweep sets.
    SHORT_INACTIVE = "SHORT_INACTIVE", "Short inactive (30+ days)"
    LONG_INACTIVE = "LONG_INACTIVE", "Long inactive (90+ days)"
    DORMANT = "DORMANT", "Dormant (365+ days)"


DECAY_TIER_THRESHOLDS_DAYS = {
    DecayTier.DORMANT: 365,
    DecayTier.LONG_INACTIVE: 90,
    DecayTier.SHORT_INACTIVE: 30,
    DecayTier.RECENT_INACTIVE: 14,
}
"""Tier → minimum days-since-signal. Walked in descending-threshold order so the
biggest matching tier wins. Tuneable; the values match the #671 spec."""
