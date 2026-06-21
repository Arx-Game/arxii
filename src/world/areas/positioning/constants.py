from django.db import models


class PositionKind(models.TextChoices):
    PRIMARY = "primary", "Primary"
    FEATURE = "feature", "Feature"  # authored region: balcony, altar, pit
    AERIAL = "aerial", "Aerial"  # reserved; auto-created by flight (#532)
    ELEVATED = "elevated", "Elevated"  # catwalk, balcony rim
    BARRIER_SIDE = "barrier_side", "Barrier Side"  # reserved; dynamic carving
    CHASM = "chasm", "Chasm"  # below-ground level; entering it emits FELL (#1018)


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
