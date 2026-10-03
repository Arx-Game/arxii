"""Backfill sets_allegiance on the two allegiance conditions that existed before #4091.

Data-only (ADR: a migration is schema-only or data-only). The names are a historical
snapshot of the rows the old name-matching code read; runtime code never matches them
again. Rows already carrying a value are left alone, so a re-run or a hand edit is safe.
If production renamed either row, this matches nothing and the required-content
dashboard's allegiance row reports the gap (#4091).
"""

from django.db import migrations

_BACKFILL = (("Charmed", "ally"), ("Calm", "neutral"))


def forwards(apps, schema_editor):
    ConditionTemplate = apps.get_model("arxii", "ConditionTemplate")
    for name, allegiance in _BACKFILL:
        ConditionTemplate.objects.filter(name=name, sets_allegiance="").update(
            sets_allegiance=allegiance
        )


class Migration(migrations.Migration):
    dependencies = [("arxii", "0197_allegiance_fields")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
