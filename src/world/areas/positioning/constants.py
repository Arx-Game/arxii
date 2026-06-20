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
