"""Write the check ladder's baseline and rank rows where a database has ranks (#5093).

Data-only, and the step before ``0412_checkrank_drop_min_points`` removes the stored
thresholds. From here a rank's threshold is the CHECK lane's level-N ``ModifierLevelBaseline``
and the check pipeline raises when a rank has no baseline at or below it, so a database that
holds ranks must hold the rows that replace their thresholds before the column goes.

Only a database that already has ``CheckRank`` rows is touched: an empty database (CI, a fresh
clone) is seeded by ``world.seeds``. For one that has ranks, this creates, if missing:

* a CHECK baseline for every level 1-30 (18 at level 1, 8 more each level), the same example
  ladder the seeds write. Staff-authored baseline rows are kept as they are.
* a ``CheckRank`` for every rank 0-30, named "Rank N" until staff name it. Existing ranks keep
  their names.

Not reversible beyond leaving the rows: they are additive and harmless to the old schema.
"""

from django.db import migrations

# seed-data-ok: ADR-0237 restructure backfill. Written only when the database already holds
# CheckRank rows, to replace the thresholds the next migration drops; the numbers are the seeds'
# example ladder, staff tune them in the rows afterwards.

_LEVELS = range(1, 31)
_BASELINE_AT_LEVEL_1 = 18
_BASELINE_STEP = 8


def write_ladder_rows(apps, schema_editor):
    CheckRank = apps.get_model("arxii", "CheckRank")
    ModifierLevelBaseline = apps.get_model("arxii", "ModifierLevelBaseline")
    if not CheckRank.objects.exists():
        return
    for level in _LEVELS:
        ModifierLevelBaseline.objects.get_or_create(
            lane="check",
            level=level,
            defaults={"baseline": _BASELINE_AT_LEVEL_1 + _BASELINE_STEP * (level - 1)},
        )
    for rank in range(31):
        # min_points still exists (NOT NULL, no default) until 0412 drops it, so a new row
        # fills it with the threshold the ladder now derives: 0 for rank 0, else baseline(rank).
        threshold = 0 if rank == 0 else _BASELINE_AT_LEVEL_1 + _BASELINE_STEP * (rank - 1)
        CheckRank.objects.get_or_create(
            rank=rank, defaults={"name": f"Rank {rank}", "min_points": threshold}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0417_kindled_deed_label"),
    ]

    operations = [
        migrations.RunPython(write_ladder_rows, migrations.RunPython.noop),
    ]
