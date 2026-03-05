"""Rename ModifierType to ModifierTarget.

This is a pure rename - the db_table stays as 'mechanics_modifiertype'
via Meta.db_table on the new model, so no data migration is needed.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("codex", "0002_initial"),
        ("conditions", "0003_remove_conditioncapabilityeffect_effect_type_and_more"),
        ("distinctions", "0002_initial"),
        ("goals", "0001_initial"),
        ("magic", "0005_add_source_cantrip_to_technique"),
        ("mechanics", "0001_initial"),
        ("relationships", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ModifierType",
            new_name="ModifierTarget",
        ),
        migrations.AlterModelOptions(
            name="modifiertarget",
            options={
                "ordering": ["category__display_order", "display_order", "name"],
            },
        ),
        migrations.AlterModelTable(
            name="modifiertarget",
            table="mechanics_modifiertype",
        ),
    ]
