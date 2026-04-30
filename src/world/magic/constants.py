from django.db import models


class CantripArchetype(models.TextChoices):
    ATTACK = "attack", "Attack"
    DEFENSE = "defense", "Defense"
    BUFF = "buff", "Buff"
    DEBUFF = "debuff", "Debuff"
    UTILITY = "utility", "Utility"


class AlterationKind(models.TextChoices):
    """Discriminator on MagicalAlterationTemplate (MAGE_SCAR vs CORRUPTION_TWIST)."""

    MAGE_SCAR = "MAGE_SCAR", "Mage Scar"
    CORRUPTION_TWIST = "CORRUPTION_TWIST", "Corruption Twist"


class AlterationTier(models.IntegerChoices):
    """Severity tier for magical alterations. Higher = more dramatic."""

    COSMETIC_TOUCH = 1, "Cosmetic Touch"
    MARKED = 2, "Marked"
    TOUCHED = 3, "Touched"
    MARKED_PROFOUNDLY = 4, "Marked Profoundly"
    REMADE = 5, "Remade"


class PendingAlterationStatus(models.TextChoices):
    """Lifecycle status of a PendingAlteration."""

    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"
    STAFF_CLEARED = "staff_cleared", "Staff Cleared"


# Tier cap configuration. Keys are AlterationTier values.
# Each value is a dict with: social_cap, weakness_cap, resonance_cap,
# visibility_required (bool).
ALTERATION_TIER_CAPS: dict[int, dict[str, int | bool]] = {
    AlterationTier.COSMETIC_TOUCH: {
        "social_cap": 1,
        "weakness_cap": 1,
        "resonance_cap": 1,
        "visibility_required": False,
    },
    AlterationTier.MARKED: {
        "social_cap": 2,
        "weakness_cap": 2,
        "resonance_cap": 2,
        "visibility_required": False,
    },
    AlterationTier.TOUCHED: {
        "social_cap": 3,
        "weakness_cap": 3,
        "resonance_cap": 3,
        "visibility_required": False,
    },
    AlterationTier.MARKED_PROFOUNDLY: {
        "social_cap": 5,
        "weakness_cap": 5,
        "resonance_cap": 5,
        "visibility_required": True,
    },
    AlterationTier.REMADE: {
        "social_cap": 8,
        "weakness_cap": 8,
        "resonance_cap": 7,
        "visibility_required": True,
    },
}

# Minimum description length for player-authored alteration descriptions.
MIN_ALTERATION_DESCRIPTION_LENGTH = 40


class TargetKind(models.TextChoices):
    TRAIT = "TRAIT", "Trait"
    TECHNIQUE = "TECHNIQUE", "Technique"
    FACET = "FACET", "Facet"
    ROOM = "ROOM", "Room"
    RELATIONSHIP_TRACK = "RELATIONSHIP_TRACK", "Relationship Track"
    RELATIONSHIP_CAPSTONE = "RELATIONSHIP_CAPSTONE", "Relationship Capstone"
    COVENANT_ROLE = "COVENANT_ROLE", "Covenant Role"


class EffectKind(models.TextChoices):
    FLAT_BONUS = "FLAT_BONUS", "Flat Bonus"
    INTENSITY_BUMP = "INTENSITY_BUMP", "Intensity Bump"
    VITAL_BONUS = "VITAL_BONUS", "Vital Bonus"
    CAPABILITY_GRANT = "CAPABILITY_GRANT", "Capability Grant"
    NARRATIVE_ONLY = "NARRATIVE_ONLY", "Narrative Only"


class VitalBonusTarget(models.TextChoices):
    MAX_HEALTH = "MAX_HEALTH", "Max Health"
    DAMAGE_TAKEN_REDUCTION = "DAMAGE_TAKEN_REDUCTION", "Damage Taken Reduction"


class RitualExecutionKind(models.TextChoices):
    SERVICE = "SERVICE", "Service"
    FLOW = "FLOW", "Flow"


class SoulTetherRole(models.TextChoices):
    ABYSSAL = "ABYSSAL", "Abyssal Side"
    SINEATER = "SINEATER", "Sineater Side"


class GainSource(models.TextChoices):
    """Discriminator for ResonanceGrant audit rows. Identifies which
    typed source FK is populated on a given grant row."""

    POSE_ENDORSEMENT = "POSE_ENDORSEMENT", "Pose endorsement"
    SCENE_ENTRY = "SCENE_ENTRY", "Scene entry endorsement"
    ROOM_RESIDENCE = "ROOM_RESIDENCE", "Room residence trickle"
    OUTFIT_TRICKLE = "OUTFIT_TRICKLE", "Outfit trickle"
    STAFF_GRANT = "STAFF_GRANT", "Staff grant"


# FACET anchor cap tuning (Spec D §6.1)
ANCHOR_CAP_FACET_DIVISOR: int = 50
"""Divisor applied to lifetime_earned(resonance) to derive FACET anchor cap.

500 lifetime resonance → cap level 10. Tunable via playtest.
"""

ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE: int = 20
"""Hard ceiling on FACET anchor cap, scaled by character path stage.

path_stage × 20 = ceiling. At stage 1, hard max = 20 (well above path cap of 10).
At stage 6, hard max = 120 (well above path cap of 60). Prevents runaway at the
extreme tail of lifetime accumulation.
"""
