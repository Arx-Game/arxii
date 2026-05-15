"""Location stat catalog and per-stat metadata.

Adding a new stat:
    1. Add a new ``StatKey`` member.
    2. Add an entry to ``STAT_DEFAULTS``, ``STAT_CLAMPS``, and
       ``SUGGESTED_CHANGE_PER_DAY``.
    3. Run ``arx manage makemigrations world.locations`` if a Django
       migration is needed (TextChoices changes emit a no-op DB migration).
"""

from __future__ import annotations

from django.db import models


class LocationParentType(models.TextChoices):
    """Discriminator for Location*Stat rows: which FK is active."""

    AREA = "area", "Area"
    ROOM = "room", "Room"


class KeyType(models.TextChoices):
    """Which field carries the cascade row's key.

    STAT → ``stat_key`` (CharField, StatKey enum).
    RESONANCE → ``resonance`` (FK to ``magic.Resonance``).

    Exactly one is populated per row; the model's ``clean()`` validates
    via DiscriminatorMixin._validate_discriminator.
    """

    STAT = "stat", "Stat"
    RESONANCE = "resonance", "Resonance"


# Default magnitude used by tag_room_resonance and any other "tag the room
# with this resonance" callers. Authors can re-tune per room afterwards via
# direct LocationStatModifier edits. 100 is a starting baseline that sits in
# the middle of any plausible per-resonance scale.
RESONANCE_DEFAULT_MAGNITUDE: int = 100


class StatKey(models.TextChoices):
    """Catalog of location ambient stats.

    Stats cascade through the area hierarchy and may be authored at any
    level (continent, kingdom, region, city, ward, neighborhood, building,
    or individual room). See LocationStatOverride and LocationStatModifier
    for cascade semantics.
    """

    CRIME = "crime", "Crime"
    ORDER = "order", "Order"
    CLEANLINESS = "cleanliness", "Cleanliness"
    LIGHTING = "lighting", "Lighting"
    NOISE = "noise", "Noise"
    TRAFFIC = "traffic", "Traffic"


# Per-stat default value when no row exists in the cascade chain.
STAT_DEFAULTS: dict[StatKey, int] = {
    StatKey.CRIME: 0,
    StatKey.ORDER: 50,
    StatKey.CLEANLINESS: 50,
    StatKey.LIGHTING: 0,
    StatKey.NOISE: 50,
    StatKey.TRAFFIC: 50,
}

# Inclusive (min, max) bounds applied to the final cascade-resolved value.
# LIGHTING is signed and symmetric around 0: -2 = pitch dark, 0 = normal
# daylight / no modifier, +2 = blinding bright. Other stats are non-negative
# and 0-anchored at one end of the clamp range.
STAT_CLAMPS: dict[StatKey, tuple[int, int]] = {
    StatKey.CRIME: (0, 100),
    StatKey.ORDER: (0, 100),
    StatKey.CLEANLINESS: (0, 100),
    StatKey.LIGHTING: (-2, 2),
    StatKey.NOISE: (0, 100),
    StatKey.TRAFFIC: (0, 100),
}

# Suggested ``change_per_day`` value for new modifiers if the calling
# system has no opinion. Negative values decay toward zero; positive
# values grow; zero is permanent. Per-row override always wins.
SUGGESTED_CHANGE_PER_DAY: dict[StatKey, int] = {
    StatKey.CRIME: -1,
    StatKey.ORDER: 0,
    StatKey.CLEANLINESS: -1,
    StatKey.LIGHTING: 0,
    StatKey.NOISE: -2,
    StatKey.TRAFFIC: -1,
}


class HolderType(models.TextChoices):
    """Discriminator for owner/tenant rows: which holder FK is active."""

    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
