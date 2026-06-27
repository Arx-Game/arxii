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
    # DRY pairs with WET as the moisture axis (#1522): climate designates a region wet or dry.
    # Unlike WET, dryness seeps everywhere (a roof doesn't stop dry air), so DRY is NOT
    # enclosure-gated — it's countered by fixtures (water features / humidity), like temperature.
    DRY = "dry", "Dry exposure"
    # Positive comfort axis (#1514): luxury decorations + magical comfort that push the comfort
    # POOL above neutral toward 6–10. Distinct from mitigation (which only cancels discomfort,
    # floored): amenities are how you ADD comfort, and the high end is deliberately expensive.
    AMENITY = "amenity", "Amenity (positive comfort)"


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
    StatKey.DRY: 0,
    StatKey.AMENITY: 0,
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
    # Wide ceilings: comfort points run to ±tens-of-thousands (weather + wounds + magic all
    # pour into one pool), so each axis needs headroom. Magnitudes are a PLACEHOLDER author pass.
    StatKey.COLD: (0, 100_000),
    StatKey.HEAT: (0, 100_000),
    StatKey.WET: (0, 100_000),
    StatKey.WIND: (0, 100_000),
    StatKey.DRY: (0, 100_000),
    StatKey.AMENITY: (0, 1_000_000),
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
    StatKey.DRY: 0,
    StatKey.AMENITY: 0,
}

# Environmental discomfort axes that sum into the comfort score (#1514).
EXPOSURE_STAT_KEYS: tuple[StatKey, ...] = (
    StatKey.COLD,
    StatKey.HEAT,
    StatKey.WET,
    StatKey.WIND,
    StatKey.DRY,
)

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

# ---------------------------------------------------------------------------
# Comfort level (#1514): a 1–10 scale derived from a wide points pool.
# ---------------------------------------------------------------------------
#
# comfort_points = amenities − felt discomfort − condition penalties (+ buffs). The pool is
# wide and sharply-growing because everything (weather, wounds, fatigue, luxury, magic) pours
# in. It maps to a 1–10 LEVEL, with 5 = neutral ("Fine", roughly 0–100 points), 10 ≈ unreachable
# without heavy magic + absurd money, 1 ≈ miserable. The level drives an AP-regen multiplier.
#
# COMFORT_LEVEL_FLOORS: the minimum points for each level, ascending. A points value resolves to
# the highest level whose floor it meets. PLACEHOLDER, anchored to Apostate's numbers (0–100=L5,
# ±10k ends, exponential between) — the band cuts are a tunable author pass; the *shape* is fixed.
COMFORT_LEVEL_FLOORS: tuple[tuple[int, int], ...] = (
    (10_000, 10),  # ≥10k — nearly impossible (heavy magic + absurd money)
    (6_000, 9),
    (2_500, 8),  # difficult but realistic
    (600, 7),
    (100, 6),
    (0, 5),  # 0–100 = "Fine" baseline
    (-800, 4),
    (-3_000, 3),
    (-10_000, 2),
    # anything below the last floor is level 1 (handled in the resolver)
)

COMFORT_LEVEL_MIN = 1
COMFORT_LEVEL_MAX = 10
COMFORT_LEVEL_NEUTRAL = 5

# AP-regen multiplier (percent adjustment) per comfort level (#1514) — Apostate's exact table.
# Level 5 (neutral) = 0; comfortable homes regen faster, miserable ones slower.
AP_REGEN_MULTIPLIER_PCT: dict[int, int] = {
    1: -50,
    2: -25,
    3: -10,
    4: -5,
    5: 0,
    6: 5,
    7: 10,
    8: 25,
    9: 50,
    10: 100,
}

# The mechanics ModifierCategory + AP-regen ModifierTargets the comfort→AP effect writes (#1514).
# get_or_create'd by world.locations.comfort_effect (otherwise only seeded in tests). The comfort
# delta (comfort_level − COMFORT_LEVEL_NEUTRAL) is a flat additive on these targets; the regen
# cron sums it for free, and its own max(0, …) floors regen — comfort can't drive it negative.
AP_MODIFIER_CATEGORY = "action_points"
AP_REGEN_TARGET_NAMES: tuple[str, ...] = ("ap_daily_regen", "ap_weekly_regen")


# Player-facing word per comfort level for the in-room readout (#1514). PLACEHOLDER — these
# are flavour the author pass will revise; the level numbers + multiplier are the real spec.
COMFORT_LEVEL_LABELS: dict[int, str] = {
    1: "Miserable",  # PLACEHOLDER
    2: "Wretched",  # PLACEHOLDER
    3: "Harsh",  # PLACEHOLDER
    4: "Uncomfortable",  # PLACEHOLDER
    5: "Fine",  # PLACEHOLDER
    6: "Pleasant",  # PLACEHOLDER
    7: "Comfortable",  # PLACEHOLDER
    8: "Snug",  # PLACEHOLDER
    9: "Luxurious",  # PLACEHOLDER
    10: "Sublime",  # PLACEHOLDER
}


class HolderType(models.TextChoices):
    """Discriminator for owner/tenant rows: which holder FK is active."""

    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
