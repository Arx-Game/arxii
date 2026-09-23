"""Data step for #3983 Plan B: carry ``HouseClaim.lands_writeup`` forward into a
``HouseClaimLand`` row on the claim's own title before the column is dropped
(0157). ADR-0237 restructure — the free-text writeup becomes the claimed
title's own land row's ``description`` rather than being discarded.

Schema-only in the SAME migration would violate the schema/data split
(``django_notes.md`` — a ``RunPython`` followed by a schema op can deadlock on
a pending FK trigger event mid-deploy), so the ``RemoveField`` is its own
migration (0157), after this one.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    HouseClaim = apps.get_model("arxii", "HouseClaim")
    HouseClaimLand = apps.get_model("arxii", "HouseClaimLand")
    for claim in HouseClaim.objects.exclude(lands_writeup=""):
        HouseClaimLand.objects.get_or_create(
            claim=claim,
            title_id=claim.title_id,
            defaults={"description": claim.lands_writeup},
        )


class Migration(migrations.Migration):
    dependencies = [("arxii", "0155_founder_columns")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
