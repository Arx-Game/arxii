"""Convert batch 4 of the authored point difficulties into levels and tenths (#5093).

Data-only (ADR-0237 restructure): every authored row keeps its difficulty. A standalone
point difficulty becomes a level: the old rank it reached on the nine-rank ladder
(0/10/25/50/80/115/155/200/250), mapped to the level whose new baseline
(18 + 8 x (level - 1)) is nearest that rank's old threshold; 0 stays level 0. A difficulty
added on top of another one, or a per-step increment, becomes tenths of a level's width:
points x 10 / 5 (the old ladder spent 5 points a level). Null stays null.

Idempotent: each pass recomputes the new column from the old one, which is untouched until the
contract migration. Reversible: the reverse fills the old column from the new one, mapping a
level back to the old threshold of the highest rank that converts at or below it, and tenths
back to points.
"""

from decimal import Decimal

from django.db import migrations

OLD_RANK_THRESHOLDS = (0, 10, 25, 50, 80, 115, 155, 200, 250)
LEVELS = range(31)


def _new_baseline(level):
    return 0 if level == 0 else 18 + 8 * (level - 1)


def points_to_level(points):
    """The level an old point difficulty converts to (ties go to the lower level)."""
    points = max(points, 0)  # a negative authored value reads as no difficulty
    rank = max(i for i, t in enumerate(OLD_RANK_THRESHOLDS) if t <= points)
    threshold = OLD_RANK_THRESHOLDS[rank]
    return min(LEVELS, key=lambda level: (abs(_new_baseline(level) - threshold), level))


def level_to_points(level):
    """The old point difficulty a level reverses to: the threshold of the highest rank at or below."""
    best = 0
    for threshold in OLD_RANK_THRESHOLDS:
        if points_to_level(threshold) <= level:
            best = threshold
    return best


def points_to_tenths(points):
    return points * 2


def tenths_to_points(tenths):
    if isinstance(tenths, Decimal):
        return tenths / 2
    return round(tenths / 2)


LEVEL = "level"
TENTHS = "tenths"

# (model, old point column, new column, kind)
COLUMNS = (
    ("challengetemplate", "severity", "severity_level", LEVEL),
    ("challengeinstance", "severity_adjustment", "severity_adjustment_tenths", TENTHS),
)


def _convert(apps, forward):
    for model_name, old, new, kind in COLUMNS:
        model = apps.get_model("arxii", model_name)
        source, target = (old, new) if forward else (new, old)
        if forward:
            convert = points_to_level if kind == LEVEL else points_to_tenths
        else:
            convert = level_to_points if kind == LEVEL else tenths_to_points
        values = (
            model.objects.exclude(**{source: None})
            .values_list(source, flat=True)
            .order_by()
            .distinct()
        )
        for value in list(values):
            model.objects.filter(**{source: value}).update(**{target: convert(value)})


def forwards(apps, schema_editor):
    _convert(apps, forward=True)


def backwards(apps, schema_editor):
    _convert(apps, forward=False)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0432_difficulty_levels_batch4_add"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
