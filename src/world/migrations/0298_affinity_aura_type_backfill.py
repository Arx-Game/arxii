"""Designate which Affinity row is which aura (data only; slice 2 of #4659).

The one-off designation the spec allows: each Affinity whose lowercased name
equals an ``AffinityType`` value and whose ``aura_type`` is still blank gets
that value. Runtime code reads ``Affinity.aura_type`` and never matches names.
Reverse is a no-op: the field is dropped by 0296's reverse anyway.
"""

from django.db import migrations

AURA_VALUES = ("celestial", "primal", "abyssal")


def set_aura_types(apps, schema_editor):
    Affinity = apps.get_model("arxii", "Affinity")
    for affinity in Affinity.objects.filter(aura_type=""):
        value = affinity.name.lower()
        if value in AURA_VALUES:
            affinity.aura_type = value
            affinity.save(update_fields=["aura_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0297_tradition_teaching_fit_schema"),
    ]

    operations = [
        migrations.RunPython(set_aura_types, migrations.RunPython.noop),
    ]
