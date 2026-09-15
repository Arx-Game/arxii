"""Reopen every starting area still marked ``trust_required`` (#3726).

Data-only, in its own migration: ``0132`` dropped ``TRUST_REQUIRED`` from
``StartingAreaAccessLevel``, and Django's ``AlterField`` on a choices list does
not touch stored values, so a row authored under the old gate keeps the literal
``"trust_required"`` — a value no choice matches any more. Left alone it renders
as the raw string, and the admin refuses to save the row until an operator
re-picks. On production the one known such row is Ariwn's starting area, whose
gate the ruling makes wrong; reopening it is the point of the issue, not a side
effect.

``STAFF_ONLY`` rows are untouched: that gate survives the ruling.
"""

from django.db import migrations

_RETIRED_ACCESS_LEVEL = "trust_required"
_OPEN_ACCESS_LEVEL = "all"


def reopen_trust_gated_areas(apps, schema_editor):
    starting_area = apps.get_model("arxii", "StartingArea")
    starting_area.objects.filter(access_level=_RETIRED_ACCESS_LEVEL).update(
        access_level=_OPEN_ACCESS_LEVEL
    )


def noop_reverse(apps, schema_editor):
    """Irreversible in substance: which areas were gated is not recoverable."""


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0132_remove_trust_gates"),
    ]

    operations = [
        migrations.RunPython(reopen_trust_gated_areas, noop_reverse),
    ]
