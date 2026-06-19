from django.db import models


class PositionKind(models.TextChoices):
    PRIMARY = "primary", "Primary"
    FEATURE = "feature", "Feature"  # authored region: balcony, altar, pit
    AERIAL = "aerial", "Aerial"  # reserved; auto-created by flight (#532)
    ELEVATED = "elevated", "Elevated"  # catwalk, balcony rim
    BARRIER_SIDE = "barrier_side", "Barrier Side"  # reserved; dynamic carving
    CHASM = "chasm", "Chasm"  # below-ground level; entering it emits FELL (#1018)
