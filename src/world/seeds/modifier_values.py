"""Example rows for modifier levels, sizes, fractions and the taper (#4594, #5093).

Clone-bootstrap and E2E scaffolding, never tuning: every number here is an example
for staff to replace after play with the tuning dashboard's modifier pile. Create-if-
missing on natural keys, so staff edits survive a re-seed.

A modifier's value is derived (#5093): its size's fraction times one level's width, where
a level's width is the step between two ``ModifierLevelBaseline`` rows. So each lane seeds
dense baseline rows (levels 1-30) and one fraction per size, and no per-level
``ModifierValue`` row: those are overrides staff add. The sizes are shares of a Large
modifier, which is half a level on every lane (0.5): Minor 0.125, Moderate 0.25,
Exceptional 0.75, Paramount 1.0.

The check lane's rows are the rank ladder (rank N starts at level N's baseline, 18 + 8 per
level), so a Large check buff is half a rank at any level and ten tapered Large buffs move
a character about five ranks less the taper. The stat lane (#4726) values a buff to a stat
in internal stat units (stats are stored x10). The maneuver effect lanes (#4876) value a
sized modifier on a to-hit, damage or partial protection target. Each of those four lanes
seeds the level widths that make a Large modifier land on its example ladder
(``_LARGE_VALUES`` and the damage and partial protection ladders below) at levels 1, 6, 11,
16, 21 and 26: the width at a level is twice that ladder's Large value there, filled in a
straight line between the listed levels. The other sizes land within 1 of their old values.
The taper is the check lane's ratio and floor, for the kinds a read of that lane gathers.
"""

from __future__ import annotations

from decimal import Decimal

from world.checks.constants import ModifierLane, ModifierSize, ModifierSourceKind
from world.checks.modifier_models import (
    ModifierLevelBaseline,
    ModifierSizeFraction,
    ModifierTaper,
)
from world.magic.models.modifier_level import CastOutcomeLevelShift, CastPowerLevel

_LEVELS = range(1, 31)

# Typical check total of a character of each level on a check in their field (#5093): one
# row per level 1-30, 18 at level 1 and 8 more each level. These rows are the rank ladder
# (rank N starts at level N's baseline) and each level's width is the step between rows.
_LEVEL_BASELINE_START = 18
_LEVEL_BASELINE_STEP = 8
_LEVEL_BASELINES: tuple[tuple[int, int], ...] = tuple(
    (level, _LEVEL_BASELINE_START + _LEVEL_BASELINE_STEP * (level - 1)) for level in _LEVELS
)

# Each size's share of one level's width, on every lane: Large is half a level and the
# other sizes keep their old shares of Large (0.25, 0.5, 1, 1.5, 2). Paramount exists
# because a vow's size step (#4551 section 5.4) reaches it; no technique authors it.
_SIZE_FRACTIONS: tuple[tuple[int, Decimal], ...] = (
    (ModifierSize.MINOR, Decimal("0.125")),
    (ModifierSize.MODERATE, Decimal("0.25")),
    (ModifierSize.LARGE, Decimal("0.5")),
    (ModifierSize.EXCEPTIONAL, Decimal("0.75")),
    (ModifierSize.PARAMOUNT, Decimal(1)),
)

# A Large modifier's example value at levels 1, 6, 11, 16, 21 and 26 on the lanes whose
# baselines are derived from it. Check points for to-hit; stat units for the stat lane
# (the seeded STAT ``PointConversionRange`` gives 1 check point per internal stat unit
# across 1-100, ``world.seeds.checks._CONVERSION_RANGES``, so the same numbers); damage
# points against Charge's base 5 damage; percentage points against Succor's base 50%
# protection (examples, #4876).
_LARGE_VALUES: tuple[tuple[int, int], ...] = (
    (1, 3),
    (6, 10),
    (11, 16),
    (16, 23),
    (21, 30),
    (26, 36),
)
_DAMAGE_LARGE_VALUES: tuple[tuple[int, int], ...] = (
    (1, 2),
    (6, 4),
    (11, 6),
    (16, 8),
    (21, 10),
    (26, 12),
)
_PARTIAL_PROTECTION_LARGE_VALUES: tuple[tuple[int, int], ...] = (
    (1, 5),
    (6, 8),
    (11, 10),
    (16, 13),
    (21, 16),
    (26, 20),
)

# Each derived lane: its level-1 baseline total (an example, a typical stat of 20, a to-hit
# total like the check lane's, Charge's 5 damage, Succor's 50%) and the Large ladder its
# level widths are drawn from.
_LANE_SCALES: tuple[tuple[str, int, tuple[tuple[int, int], ...]], ...] = (
    (ModifierLane.STAT, 20, _LARGE_VALUES),
    (ModifierLane.TO_HIT, 18, _LARGE_VALUES),
    (ModifierLane.DAMAGE, 5, _DAMAGE_LARGE_VALUES),
    (ModifierLane.PARTIAL_PROTECTION, 50, _PARTIAL_PROTECTION_LARGE_VALUES),
)

# The Large fraction (``_SIZE_FRACTIONS``) times a width is the Large value, so a width is
# twice the Large value it must produce.
_LARGE_FRACTION_INVERSE = 2

# The owner's light taper (#4551 decision 1): each extra at 7/8, never below 2/3. The
# character's own standing (rollmod, effort, fatigue, strain, soulfray, capability) and
# combat's own-magic tilts (affinity, pull) get no row.
_TAPER_RATIO = Decimal("0.8750")
_TAPER_FLOOR = Decimal("0.6667")
_TAPERED_KINDS: tuple[str, ...] = (
    ModifierSourceKind.CONDITION,
    ModifierSourceKind.SCENE,
    ModifierSourceKind.EQUIPMENT,
    ModifierSourceKind.FASHION,
    ModifierSourceKind.CHARACTER,
    ModifierSourceKind.RELATIONSHIP,
    ModifierSourceKind.FAVOR,
)
# The kinds a stat read gathers (``TraitHandler._get_stat_modifier``): no scene, fashion,
# relationship or favor source reaches a stat. The maneuver effect read gathers the same.
_STAT_TAPERED_KINDS: tuple[str, ...] = (
    ModifierSourceKind.CONDITION,
    ModifierSourceKind.EQUIPMENT,
    ModifierSourceKind.CHARACTER,
)

# Effective cast power to modifier level, against the tier budgets (20/40/60/80/100
# power for tiers 1-5, representative levels 1/6/11/16/21).
_CAST_POWER_LEVELS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (8, 3),
    (16, 6),
    (30, 11),
    (45, 16),
    (60, 21),
    (80, 26),
)
# A Critical Success casts its buff two levels higher; a Partial Success one lower.
_CAST_OUTCOME_SHIFTS: tuple[tuple[int, int], ...] = ((0, -1), (2, 2))


def _level_widths(large_values: tuple[tuple[int, int], ...]) -> dict[int, int]:
    """One level's width at each of levels 1-29, from a Large ladder's example values.

    Twice the Large value at each listed level, a straight line between them, and the last
    listed level's width above it.
    """
    anchors = [(level, _LARGE_FRACTION_INVERSE * large) for level, large in large_values]
    widths: dict[int, int] = {}
    for level in range(1, _LEVELS[-1]):
        below = [(at, width) for at, width in anchors if at <= level]
        above = [(at, width) for at, width in anchors if at > level]
        if not above:
            widths[level] = below[-1][1]
            continue
        (low_level, low_width), (high_level, high_width) = below[-1], above[0]
        widths[level] = low_width + round(
            (high_width - low_width) * (level - low_level) / (high_level - low_level)
        )
    return widths


def _seed_fractions(lane: str) -> None:
    for size, fraction in _SIZE_FRACTIONS:
        ModifierSizeFraction.objects.get_or_create(
            lane=lane, size=size, defaults={"fraction": fraction}
        )


def _seed_taper(lane: str, kinds: tuple[str, ...]) -> None:
    for kind in kinds:
        ModifierTaper.objects.get_or_create(
            lane=lane,
            source_kind=kind,
            defaults={"ratio": _TAPER_RATIO, "floor": _TAPER_FLOOR},
        )


def _seed_derived_lane(lane: str, start: int, large_values: tuple[tuple[int, int], ...]) -> None:
    """Dense baselines (levels 1-30), size fractions and taper rows for one derived lane."""
    widths = _level_widths(large_values)
    baseline = start
    for level in _LEVELS:
        ModifierLevelBaseline.objects.get_or_create(
            lane=lane, level=level, defaults={"baseline": baseline}
        )
        baseline += widths.get(level, 0)
    _seed_fractions(lane)
    _seed_taper(lane, _STAT_TAPERED_KINDS)


def seed_check_level_baselines() -> None:
    """Create the CHECK lane's dense level baseline rows (levels 1-30), if missing.

    The rank ladder and every level width read these rows, so ``seed_check_resolution_tables``
    seeds them with the ranks.
    """
    for level, baseline in _LEVEL_BASELINES:
        ModifierLevelBaseline.objects.get_or_create(
            lane=ModifierLane.CHECK, level=level, defaults={"baseline": baseline}
        )


def seed_modifier_value_tables() -> None:
    """Create the example baseline, size fraction and taper rows for the check, stat and
    maneuver effect lanes, and the cast-level rows, if missing.

    No ``ModifierValue`` row is seeded: values are derived from the fractions and the
    baselines, and an override row is staff's to add.
    """
    seed_check_level_baselines()
    _seed_fractions(ModifierLane.CHECK)
    _seed_taper(ModifierLane.CHECK, _TAPERED_KINDS)
    for lane, start, large_values in _LANE_SCALES:
        _seed_derived_lane(lane, start, large_values)
    for min_power, level in _CAST_POWER_LEVELS:
        CastPowerLevel.objects.get_or_create(min_power=min_power, defaults={"level": level})
    for success_level, shift in _CAST_OUTCOME_SHIFTS:
        CastOutcomeLevelShift.objects.get_or_create(
            success_level=success_level, defaults={"level_shift": shift}
        )
