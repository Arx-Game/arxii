from django.db import models


class PositionKind(models.TextChoices):
    PRIMARY = "primary", "Primary"
    FEATURE = "feature", "Feature"  # authored region: balcony, altar, pit
    AERIAL = "aerial", "Aerial"  # reserved; auto-created by flight (#532)
    ELEVATED = "elevated", "Elevated"  # catwalk, balcony rim
    BARRIER_SIDE = "barrier_side", "Barrier Side"  # reserved; dynamic carving
    CHASM = "chasm", "Chasm"  # below-ground level; entering it emits FELL (#1018)


class CreatureTraversal(models.TextChoices):
    """How a mover crosses the position graph (#4607, slice 2 of #4576).

    WALKS crosses open edges only. CLIMBS and LEAPS also cross a wall that has a way
    past it (an active gating challenge) at one extra hop; they differ in narration only.
    FLIES also uses the aerial layer, so it passes over walls that do not block flight.
    """

    WALKS = "walks", "Walks"
    CLIMBS = "climbs", "Climbs"
    LEAPS = "leaps", "Leaps"
    FLIES = "flies", "Flies"


class ReactionReach(models.TextChoices):
    """How far a capability lets its holder move when she dodges an attack (#4676).

    NONE gives no dodge. IN_PLACE dodges without moving. ADJACENT may land in a place
    next to hers, ANY_PLACE anywhere in the room, AIRBORNE next door or in the air
    above her place.
    """

    NONE = "none", "No dodge"
    IN_PLACE = "in_place", "In place"
    ADJACENT = "adjacent", "An adjacent place"
    ANY_PLACE = "any_place", "Any place in the room"
    AIRBORNE = "airborne", "An adjacent place or the air above"


class ReactionCostKind(models.TextChoices):
    """What a dodge with this capability costs: anima, or fatigue for a physical one (#4676)."""

    ANIMA = "anima", "Anima"
    FATIGUE = "fatigue", "Fatigue"


AERIAL_PROPERTY_NAME = "aerial"


# Plummet content identity keys (#1228). The fall DamageType, the Falling
# ConditionCategory, and the staged Plummeting ConditionTemplate are seeded
# idempotently by ensure_fall_content(); these names locate those rows.
FALL_DAMAGE_TYPE_NAME: str = "Fall"
PLUMMETING_CONDITION_NAME: str = "Plummeting"
FALLING_CATEGORY_NAME: str = "Falling"


# "Catch the Faller" challenge content identity keys (#1228, Task 4). The
# capability-gated catch challenge, its shared target Property, the four seed
# catch CapabilityType rows, and the reused reflexes CheckType are all seeded
# idempotently by ensure_catch_content() (called from ensure_fall_content());
# these names locate those rows. Adding a new catch capability later is pure
# data: one CapabilityType + Application(target_property=the catch property) +
# ChallengeApproach row, with zero engine code.
CATCH_THE_FALLER_NAME: str = "Catch the Faller"
CATCHABLE_PROPERTY_NAME: str = "catchable"
CATCH_CHECK_TYPE_NAME: str = "Reflexes"

# Seed catch capabilities. Named only — capabilities are pure data. The whole
# point of the design is that this tuple is illustrative, not exhaustive.
FLY_CAPABILITY_NAME: str = "fly"
TELEPORT_CAPABILITY_NAME: str = "teleport"
TELEKINESIS_CAPABILITY_NAME: str = "telekinesis"
ACROBATICS_CAPABILITY_NAME: str = "acrobatics"


# FELL → plummet wiring identity key (#1228). Shared by the room-owned
# TriggerDefinition and its FlowDefinition (both named ``fall_to_plummet``),
# seeded by ``wire_fall_triggers`` and located by ``install_fall_triggers``.
# Hoisted here so the trigger/flow name has a single source of truth (#1284).
FALL_TRIGGER_NAME: str = "fall_to_plummet"


class RampartSignature(models.TextChoices):
    """The one authored behavior a RampartElementProfile grants its Ramparts (#2209).

    SEAL_EDGES: raising the rampart also seals every PositionEdge touching its
        position (Stone — a wall, not just a ward).
    MISSILE_WARD: signature_value adjusts resist against MISSILE-delivery strikes
        and area strikes (Wind).
    MELEE_RETALIATION: a blocked melee strike burns the striker back for
        signature_value of signature_damage_type (Fire) — NPCs only, ADR-0023.
    GRASPING: a CombatOpponent forced onto this rampart's position is afflicted
        with signature_condition (Thorn).
    """

    SEAL_EDGES = "seal_edges", "Seal Edges"
    MISSILE_WARD = "missile_ward", "Missile Ward"
    MELEE_RETALIATION = "melee_retaliation", "Melee Retaliation"
    GRASPING = "grasping", "Grasping"


class FeatureReach(models.TextChoices):
    """Where a feature's stunt can take someone, measured from the feature's own place."""

    ADJACENT = "adjacent", "A place next to its own"
    ANY_PLACE = "any_place", "Any place in the room"
    SAME_TYPE = "same_type", "Another place with the same feature"
    ELEVATED_ADJACENT = "elevated_adjacent", "A raised place next to its own"


class StuntOutcome(models.TextChoices):
    """How a stunt went (#4675): reached cleanly, reached roughly, or missed."""

    CLEAN = "clean", "Clean"
    PARTIAL = "partial", "Partial"
    MISSED = "missed", "Missed"


# Stunt copy (#4675, slice 3 of #4651). The player's own lines, then the room's.
STUNT_CANT_FROM_HERE = "You can't do that from here."
STUNT_CLEAN = "You use the {feature} to reach {place}."
STUNT_PARTIAL = "You reach {place}, but not cleanly."
STUNT_MISSED = "You don't make it."
STUNT_ROOM_CLEAN = "{name} uses the {feature} to reach {place}."
STUNT_ROOM_PARTIAL = "{name} uses the {feature} to reach {place}, but not cleanly."
STUNT_ROOM_MISSED = "{name} tries the {feature} and doesn't make it."


class RampartCrackState(models.TextChoices):
    """Coarse integrity band for a Rampart, read off ``Rampart.crack_state``."""

    INTACT = "intact", "Intact"
    CRACKED = "cracked", "Cracked"
    CRUMBLING = "crumbling", "Crumbling"


# Conjured wall content and tuning (#4606). A spell-made wall (Barricade) gates its
# edge with one shared challenge, minted from the authored ChallengeTemplate of this
# name (climb over / smash through, ADR-0109); seeded by
# ensure_conjured_barrier_content() and listed on the Required content dashboard.
CONJURED_BARRIER_CHALLENGE_NAME: str = "Conjured Barrier"
# A spell wall's integrity: this base plus the cast's severity (the power-scaled
# term the cast already priced onto its marker condition). Playtest tuning.
CONJURED_WALL_BASE_INTEGRITY: int = 10
