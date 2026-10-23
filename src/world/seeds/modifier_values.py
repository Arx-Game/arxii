"""Example rows for modifier levels, sizes, the value table and the taper (#4594).

Clone-bootstrap and E2E scaffolding, never tuning: every number here is an example
for staff to replace after play with the tuning dashboard's modifier pile. Create-if-
missing on natural keys, so staff edits survive a re-seed.

The check lane's step is one rank band at the character's total (#4551 section 5.5).
These examples make a Large buff about a third of a rank band for a character of its
own level, so ten tapered Large buffs move that character about two ranks.
"""

from __future__ import annotations

from decimal import Decimal

from world.checks.constants import ModifierLane, ModifierSize, ModifierSourceKind
from world.checks.modifier_models import ModifierLevelBaseline, ModifierTaper, ModifierValue
from world.magic.models.modifier_level import CastOutcomeLevelShift, CastPowerLevel

# Typical check total of a character of each level on a check in their field.
_LEVEL_BASELINES: tuple[tuple[int, int], ...] = (
    (1, 18),
    (6, 58),
    (11, 98),
    (16, 138),
    (21, 178),
    (26, 218),
)

# A Large modifier's value at each level; the other sizes are shares of it.
_LARGE_VALUES: tuple[tuple[int, int], ...] = (
    (1, 3),
    (6, 10),
    (11, 16),
    (16, 23),
    (21, 30),
    (26, 36),
)
_SIZE_SHARES: tuple[tuple[int, Decimal], ...] = (
    (ModifierSize.MINOR, Decimal("0.25")),
    (ModifierSize.MODERATE, Decimal("0.5")),
    (ModifierSize.LARGE, Decimal(1)),
    (ModifierSize.EXCEPTIONAL, Decimal("1.5")),
    (ModifierSize.PARAMOUNT, Decimal(2)),
)

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


def _scaled(value: int, share: Decimal) -> int:
    return max(1, int((Decimal(value) * share).to_integral_value()))


def seed_modifier_value_tables() -> None:
    """Create the example check-lane rows and cast-level rows, if missing."""
    for level, baseline in _LEVEL_BASELINES:
        ModifierLevelBaseline.objects.get_or_create(
            lane=ModifierLane.CHECK, level=level, defaults={"baseline": baseline}
        )
    for level, large in _LARGE_VALUES:
        for size, share in _SIZE_SHARES:
            ModifierValue.objects.get_or_create(
                lane=ModifierLane.CHECK,
                level=level,
                size=size,
                defaults={"value": _scaled(large, share)},
            )
    for kind in _TAPERED_KINDS:
        ModifierTaper.objects.get_or_create(
            lane=ModifierLane.CHECK,
            source_kind=kind,
            defaults={"ratio": _TAPER_RATIO, "floor": _TAPER_FLOOR},
        )
    for min_power, level in _CAST_POWER_LEVELS:
        CastPowerLevel.objects.get_or_create(min_power=min_power, defaults={"level": level})
    for success_level, shift in _CAST_OUTCOME_SHIFTS:
        CastOutcomeLevelShift.objects.get_or_create(
            success_level=success_level, defaults={"level_shift": shift}
        )
