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

from evennia_extensions.constants import RoomEnclosure


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
    # Environmental exposure axes (#1514 — climate → comfort). Each is a non-negative
    # *discomfort* magnitude: climate/weather/style push it up, counter-fixtures push it
    # down, and the 0-floor clamp guarantees a counter can zero out its own axis but never
    # drive it negative or touch another — so a hearth eats COLD and can never make a room
    # "too hot". See EXPOSURE_STAT_KEYS + services.comfort_score.
    COLD = "cold", "Cold exposure"
    HEAT = "heat", "Heat exposure"
    # Weather exposure axes — only *felt* when the room's enclosure doesn't shelter them
    # (a roof stops WET; walls stop WIND). The weather layer (later slice) populates them.
    WET = "wet", "Wet exposure"
    WIND = "wind", "Wind exposure"


# Per-stat default value when no row exists in the cascade chain.
STAT_DEFAULTS: dict[StatKey, int] = {
    StatKey.CRIME: 0,
    StatKey.ORDER: 50,
    StatKey.CLEANLINESS: 50,
    StatKey.LIGHTING: 0,
    StatKey.NOISE: 50,
    StatKey.TRAFFIC: 50,
    # Exposure axes default to 0 — a room with no climate/weather/style input is neutral.
    StatKey.COLD: 0,
    StatKey.HEAT: 0,
    StatKey.WET: 0,
    StatKey.WIND: 0,
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
    # The (0, …) floor is load-bearing: it is the "counters never harm" guarantee (#1514).
    StatKey.COLD: (0, 100),
    StatKey.HEAT: (0, 100),
    StatKey.WET: (0, 100),
    StatKey.WIND: (0, 100),
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
    # Climate/style/fixture contributions are permanent baselines by default (0); transient
    # weather callers (a cold snap) supply their own negative decay per-row.
    StatKey.COLD: 0,
    StatKey.HEAT: 0,
    StatKey.WET: 0,
    StatKey.WIND: 0,
}

# Environmental discomfort axes that sum into the comfort score (#1514).
EXPOSURE_STAT_KEYS: tuple[StatKey, ...] = (StatKey.COLD, StatKey.HEAT, StatKey.WET, StatKey.WIND)

# The subset of exposure axes that are *weather* reaching you physically — enclosure can
# shelter these (a roof, walls). Temperature (COLD/HEAT) is NOT here: it seeps regardless and
# is countered by fixtures/style, never by enclosure alone.
WEATHER_EXPOSURE_AXES: frozenset[StatKey] = frozenset({StatKey.WET, StatKey.WIND})

# Which weather axes each enclosure level fully shelters (#1514). The 0-floor model means
# "sheltered" = felt as 0. A roof stops rain/snow; walls also stop wind. SEALED matches WALLED
# for weather — its extra value (temperature insulation) is a later fixtures/style slice.
ENCLOSURE_SHELTERED_AXES: dict[RoomEnclosure, frozenset[StatKey]] = {
    RoomEnclosure.OPEN_AIR: frozenset(),
    RoomEnclosure.ROOFED: frozenset({StatKey.WET}),
    RoomEnclosure.WALLED: frozenset({StatKey.WET, StatKey.WIND}),
    RoomEnclosure.SEALED: frozenset({StatKey.WET, StatKey.WIND}),
}


class HolderType(models.TextChoices):
    """Discriminator for owner/tenant rows: which holder FK is active."""

    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
