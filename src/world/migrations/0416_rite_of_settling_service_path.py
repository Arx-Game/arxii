"""The drift correction rite's service function is renamed, so its stored path follows (#5124).

Data only. ``Ritual.service_function_path`` is staff-authored content: the Rite of Drift
Correction carries the dotted path of the function it runs. #5124 replaced that function
with ``perform_settling_rite`` (the rite of settling), so a row still holding the old path
would name a function that no longer exists. This rewrites the path on every ``Ritual`` row
holding the old one; a database with no such row (a fresh one, or one whose staff never made
the rite) changes nothing, and running it twice changes nothing.

Reversing puts the old path back on every row holding the new one.
"""

from django.db import migrations

OLD_PATH = "world.magic.services.drift_correction.perform_drift_correction_rite"
NEW_PATH = "world.magic.services.drift_correction.perform_settling_rite"


def _rewrite(apps, old, new):
    Ritual = apps.get_model("arxii", "Ritual")
    Ritual.objects.filter(service_function_path=old).update(service_function_path=new)


def to_settling_rite(apps, schema_editor):
    _rewrite(apps, OLD_PATH, NEW_PATH)


def to_drift_correction_rite(apps, schema_editor):
    _rewrite(apps, NEW_PATH, OLD_PATH)


class Migration(migrations.Migration):
    dependencies = [("arxii", "0415_kindling_situation_choices")]

    operations = [
        migrations.RunPython(to_settling_rite, to_drift_correction_rite),
    ]
