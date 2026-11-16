"""Derive modifier values from size fractions and level widths, keeping edited rows (#5093).

Data-only, after ``0420_modifier_size_fraction`` adds ``ModifierSizeFraction``. A modifier's
value is now its size's fraction times one level's width, and a ``ModifierValue`` row is an
override of that at one exact level. A database that holds ``ModifierValue`` rows is touched
lane by lane:

1. The lane's size fractions and dense level baselines (levels 1-30) are created if missing,
   the same example rows ``world.seeds.modifier_values`` writes, so that deleting a row below
   never leaves a sized modifier with no value. Staff-authored fractions and baselines are
   kept as they are.
2. Each ``ModifierValue`` row still equal to the value the old seed wrote for its lane, level
   and size is deleted: the derived value replaces it. A row staff edited (any other value, or
   a level the seed never wrote) is kept as an override.

Data disposition (ADR-0237): restructure for the fraction and baseline rows (created, never
overwritten), deliberate discard for the deleted rows. The discarded rows are only those equal
to the old example seed, so no staff-authored number is deleted. The discard is a deliberate
rescale: on the check lane a Large buff is now half a level (4 points everywhere) where the old
example ladder gave 3 to 36 by level, and the other lanes land within 1 of their old Large
values at the seeded levels and move in a straight line between them. Rows kept as overrides
now cover only their own exact level, where before a row covered every level up to the next
authored one. The count of rows deleted and kept per lane is logged at WARNING so the deploy
log carries it. Production held no ModifierValue rows when this was written (2026-11-15
dump), so a production run finds no lane to touch and does nothing.

Not reversible: the deleted rows are an example seed, and the reverse is a no-op.
"""

from decimal import Decimal
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# seed-data-ok: ADR-0237 restructure backfill. Written only for a lane that already holds
# ModifierValue rows, so a fresh database (CI, a clone) is untouched and seeded by world.seeds;
# the numbers are the seeds' example rows, staff tune them in the rows afterwards.

_LEVELS = range(1, 31)
_CHECK_LANE = "check"

# The sizes (ModifierSize values) and the shares of a Large modifier the old seed wrote.
_OLD_SHARES = (
    (1, Decimal("0.25")),
    (2, Decimal("0.5")),
    (3, Decimal(1)),
    (4, Decimal("1.5")),
    (5, Decimal(2)),
)
# The size fractions the new seed writes for every lane (Large is half a level).
_FRACTIONS = (
    (1, Decimal("0.125")),
    (2, Decimal("0.25")),
    (3, Decimal("0.5")),
    (4, Decimal("0.75")),
    (5, Decimal(1)),
)

_LARGE_VALUES = ((1, 3), (6, 10), (11, 16), (16, 23), (21, 30), (26, 36))
_DAMAGE_LARGE_VALUES = ((1, 2), (6, 4), (11, 6), (16, 8), (21, 10), (26, 12))
_PARTIAL_PROTECTION_LARGE_VALUES = ((1, 5), (6, 8), (11, 10), (16, 13), (21, 16), (26, 20))

# lane -> (level-1 baseline, Large ladder). The check lane's baselines are 18 + 8 per level
# (the rank ladder), so its widths are 8 and need no ladder.
_DERIVED_LANES = {
    "stat": (20, _LARGE_VALUES),
    "to_hit": (18, _LARGE_VALUES),
    "damage": (5, _DAMAGE_LARGE_VALUES),
    "partial_protection": (50, _PARTIAL_PROTECTION_LARGE_VALUES),
}
_OLD_LARGE_LADDERS = {
    "check": _LARGE_VALUES,
    "stat": _LARGE_VALUES,
    "to_hit": _LARGE_VALUES,
    "damage": _DAMAGE_LARGE_VALUES,
    "partial_protection": _PARTIAL_PROTECTION_LARGE_VALUES,
}


def _old_seeded_values(lane):
    """The (level, size) -> value rows the old seed wrote for ``lane``."""
    values = {}
    for level, large in _OLD_LARGE_LADDERS[lane]:
        for size, share in _OLD_SHARES:
            scaled = max(1, int((Decimal(large) * share).to_integral_value()))
            values[(level, size)] = scaled
    return values


def _level_widths(large_values):
    """One level's width at levels 1-29: twice the Large value, a line between listed levels."""
    anchors = [(level, 2 * large) for level, large in large_values]
    widths = {}
    for level in range(1, 30):
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


def _lane_baselines(lane):
    if lane == _CHECK_LANE:
        return [(level, 18 + 8 * (level - 1)) for level in _LEVELS]
    start, large_values = _DERIVED_LANES[lane]
    widths = _level_widths(large_values)
    baseline, rows = start, []
    for level in _LEVELS:
        rows.append((level, baseline))
        baseline += widths.get(level, 0)
    return rows


def derive_values_from_fractions(apps, schema_editor):
    ModifierValue = apps.get_model("arxii", "ModifierValue")
    ModifierSizeFraction = apps.get_model("arxii", "ModifierSizeFraction")
    ModifierLevelBaseline = apps.get_model("arxii", "ModifierLevelBaseline")
    for lane in _OLD_LARGE_LADDERS:
        rows = list(ModifierValue.objects.filter(lane=lane))
        if not rows:
            continue
        for size, fraction in _FRACTIONS:
            ModifierSizeFraction.objects.get_or_create(
                lane=lane, size=size, defaults={"fraction": fraction}
            )
        for level, baseline in _lane_baselines(lane):
            ModifierLevelBaseline.objects.get_or_create(
                lane=lane, level=level, defaults={"baseline": baseline}
            )
        seeded = _old_seeded_values(lane)
        equal_ids = [row.pk for row in rows if seeded.get((row.level, row.size)) == row.value]
        ModifierValue.objects.filter(pk__in=equal_ids).delete()
        logger.warning(
            "ModifierValue %s lane: deleted %d rows equal to the old seed, kept %d as overrides.",
            lane,
            len(equal_ids),
            len(rows) - len(equal_ids),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0420_modifier_size_fraction"),
    ]

    operations = [
        migrations.RunPython(derive_values_from_fractions, migrations.RunPython.noop),
    ]
