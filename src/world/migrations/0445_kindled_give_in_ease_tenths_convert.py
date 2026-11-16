"""Convert the kindled strengths' control-roll ease from points to tenths of a level (#5093).

Data-only (ADR-0237 restructure): every strength row keeps its ease. ``give_in_ease`` was a
difficulty reduction in points on the Fury control roll, so it is an increment and converts
the way every other per-step increment does: tenths = points x 2 (the old ladder spent 5
points a level, so one point is two tenths of a level's width). It is read through
``difficulty_step_points`` at the Fury tier's base check level.

Idempotent: each pass recomputes the new column from the old one, which is untouched until
``0446_kindled_give_in_ease_remove``. Reversible: the reverse fills the old column from the
new one (tenths / 2, rounded).
"""

from django.db import migrations


def points_to_tenths(points):
    return points * 2


def tenths_to_points(tenths):
    return round(tenths / 2)


def _convert(apps, forward):
    KindledStrengthTier = apps.get_model("arxii", "KindledStrengthTier")
    source, target = (
        ("give_in_ease", "give_in_ease_tenths")
        if forward
        else ("give_in_ease_tenths", "give_in_ease")
    )
    convert = points_to_tenths if forward else tenths_to_points
    values = KindledStrengthTier.objects.values_list(source, flat=True).order_by().distinct()
    for value in list(values):
        KindledStrengthTier.objects.filter(**{source: value}).update(**{target: convert(value)})


def forwards(apps, schema_editor):
    _convert(apps, forward=True)


def backwards(apps, schema_editor):
    _convert(apps, forward=False)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0444_kindled_give_in_ease_tenths_add"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
