from django.db import models


class CantripArchetype(models.TextChoices):
    ATTACK = "attack", "Attack"
    DEFENSE = "defense", "Defense"
    BUFF = "buff", "Buff"
    DEBUFF = "debuff", "Debuff"
    UTILITY = "utility", "Utility"


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
    ITEM = "ITEM", "Item"
    ROOM = "ROOM", "Room"
    RELATIONSHIP_TRACK = "RELATIONSHIP_TRACK", "Relationship Track"
    RELATIONSHIP_CAPSTONE = "RELATIONSHIP_CAPSTONE", "Relationship Capstone"


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


# Item-typeclass paths registered for ThreadWeavingUnlock(target_kind=ITEM).
# Spec §2.1 line 332 — validated at save(); subclasses inherit eligibility
# via typeclass-inheritance walk in eligibility checks.
THREADWEAVING_ITEM_TYPECLASSES: tuple[str, ...] = (
    # Populate during Phase 5 / authoring pass — start with whatever item
    # typeclasses already exist in src/typeclasses/items.py and weapons.py.
    # For Phase 1, the registry exists with at minimum the base paths Spec §6.4
    # references: swords, daggers, polearms, holy symbols, tomes, etc.
    # The exact list is content; the registry shape is the contract.
)
