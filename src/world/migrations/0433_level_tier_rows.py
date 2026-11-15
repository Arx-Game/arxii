"""Write the tier jump rows on a database that already has check level baselines (#5093).

Data-only, after ``0432_level_tier`` (the table). The tier jump is new behaviour: power jumps
sharply on crossing into a new tier, at levels 6, 11, 16, 21 and 26, each worth 24 points (three
ranks at the 8-point level width the check baselines are seeded at). Production already holds
the check baselines, so without these rows it would never get the jump. A database with no check
baselines (a fresh one, which the seeds fill) is left alone, and so is one that already holds
any tier row: staff own the tiers then, and a start level moved or deleted must not come back.

Data disposition (ADR-0237): additive. Nothing is dropped or rewritten. Not reversible beyond
leaving the rows, which are harmless to the old schema.
"""

from django.db import migrations

# seed-data-ok: additive backfill of the tier jump's starting rows for a database that already
# holds the check baselines; staff tune each row afterwards.

_TIERS = ((6, 24), (11, 24), (16, 24), (21, 24), (26, 24))


def write_tier_rows(apps, schema_editor):
    ModifierLevelBaseline = apps.get_model("arxii", "ModifierLevelBaseline")
    LevelTier = apps.get_model("arxii", "LevelTier")
    if not ModifierLevelBaseline.objects.filter(lane="check").exists():
        return
    if LevelTier.objects.exists():
        return
    for start_level, bonus_points in _TIERS:
        LevelTier.objects.create(start_level=start_level, bonus_points=bonus_points)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0432_level_tier"),
    ]

    operations = [
        migrations.RunPython(write_tier_rows, migrations.RunPython.noop),
    ]
