"""Reverse-only data step for the affinity contract (#4681; data only).

Forwards is a no-op: 0303 already copied everything into the row-keyed FKs. Backwards runs
after the contract migration is undone, when the old enum CharFields exist again with
blank defaults, and refills them from the FKs so the unique keys 0304 restores hold real
values. Covers every column the contract re-adds: the enum CharFields and the three
``CharacterAura`` percentages (from ``CharacterAuraShare``); the removed config columns
are not restored (they were constants, and the old code is not running on a rollback).
"""

from django.db import migrations

# (model, old CharField, FK that replaced it)
_COPIES = (
    ("CombatOpponent", "affinity", "affinity_ref"),
    ("AuraAffinityThreshold", "affinity", "affinity_ref"),
    ("ResonanceConversion", "target_affinity", "target_affinity_ref"),
    ("FallRedemptionRecord", "from_affinity", "from_affinity_ref"),
    ("FallRedemptionRecord", "to_affinity", "to_affinity_ref"),
    ("VowAddedEffect", "affinity", "affinity_ref"),
    ("VowSituationalPerkRung", "affinity", "affinity_ref"),
    ("VowSituationalPerkSituation", "affinity", "affinity_ref"),
)


def _noop(apps, schema_editor):
    return


def restore_old_columns(apps, schema_editor):
    affinity_model = apps.get_model("arxii", "Affinity")
    for model_name, old, new in _COPIES:
        model = apps.get_model("arxii", model_name)
        for affinity in affinity_model.objects.all():
            model.objects.filter(**{new: affinity}).update(**{old: affinity.name.lower()})
    share_model = apps.get_model("arxii", "CharacterAuraShare")
    aura_model = apps.get_model("arxii", "CharacterAura")
    for share in share_model.objects.select_related("affinity"):
        column = share.affinity.name.lower()
        if column in ("celestial", "primal", "abyssal"):
            aura_model.objects.filter(pk=share.aura_id).update(**{column: share.percent})


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0305_affinity_rows_unique_released"),
    ]

    operations = [
        migrations.RunPython(_noop, restore_old_columns),
    ]
