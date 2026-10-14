"""Restate stored standoff reveals of kind "regard" as "faction_rule" (#4354, spec item 15).

Data only. ``StandoffReveal`` is play state (a live standoff's reads), so the rows are
rewritten in place; the reveal constraints were dropped by the previous migration and
come back in the next one, against the new value.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    StandoffReveal = apps.get_model("arxii", "StandoffReveal")
    StandoffReveal.objects.filter(kind="regard").update(kind="faction_rule")


def backwards(apps, schema_editor):
    StandoffReveal = apps.get_model("arxii", "StandoffReveal")
    StandoffReveal.objects.filter(kind="faction_rule").update(kind="regard")


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0223_rename_faction_rules_and_angles"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
