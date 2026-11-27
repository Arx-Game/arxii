"""Mark the four bonus targets character creation uses up (#5206).

The migration before this one added ``ModifierTarget.spent_at_creation``, False on every
row. The sheet's Bonuses band leaves out a target marked with it. This sets it on the four
targets named in the spec's call 12, each matched by its category's name and its own name,
both case-insensitively as the natural key compares them (ADR-0163): the technique picks
and the training pool creation reads, the statistics budget's free points, and the height
band bonus.

This migration creates no row and writes no other column. A target a database does not
hold is skipped. The names are copied from ``world.character_creation.constants``
(``CG_MODIFIER_CATEGORY``, ``STARTING_TECHNIQUE_PICKS_TARGET``,
``MAGIC_TRAINING_POINTS_TARGET``) and ``world.mechanics.constants.STAT_CATEGORY_NAME`` as
they stood when this was written; migrations do not import application code.
"""

from django.db import migrations

SPENT_AT_CREATION = (
    ("character_creation", "starting_technique_picks"),
    ("character_creation", "magic_training_points"),
    ("stat", "attribute_free_points"),
    ("height_band", "max_height_band_bonus"),
)


def mark_spent_at_creation(apps, schema_editor):
    ModifierTarget = apps.get_model("arxii", "ModifierTarget")
    for category_name, target_name in SPENT_AT_CREATION:
        ModifierTarget.objects.filter(
            category__name__iexact=category_name, name__iexact=target_name
        ).update(spent_at_creation=True)


def unmark_spent_at_creation(apps, schema_editor):
    ModifierTarget = apps.get_model("arxii", "ModifierTarget")
    for category_name, target_name in SPENT_AT_CREATION:
        ModifierTarget.objects.filter(
            category__name__iexact=category_name, name__iexact=target_name
        ).update(spent_at_creation=False)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0485_modifiertarget_spent_at_creation"),
    ]

    operations = [
        migrations.RunPython(mark_spent_at_creation, unmark_spent_at_creation),
    ]
