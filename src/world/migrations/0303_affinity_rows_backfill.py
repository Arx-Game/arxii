"""Data-only backfill for the row-keyed affinity expand (#4681, migration 0302).

ADR-0237 disposition per table (nothing is dropped here; the old CharFields stay):

- ``ResonanceConversion.target_affinity`` and the covenant situation ``affinity``
  (``VowSituationalPerkSituation``, ``VowSituationalPerkRung``, ``VowAddedEffect``):
  RESTRUCTURE. Production holds authored rows (16 conversions, 1 abyssal situation);
  each lowercase enum value is resolved to its ``Affinity`` row and copied into the
  ``_ref`` FK. A value with no matching row raises; blank stays null.
- ``FallRedemptionConfig`` / ``CorruptionConfig``: CONSTANTS. Production holds one
  row each at the model defaults; their values are written onto the six cross
  ``AffinityInteraction`` pairs and ``Affinity.corruption_coefficient``. An absent
  config row falls back to the model defaults. A missing pair raises.
- ``CharacterAura``, ``CombatOpponent``, ``AuraAffinityThreshold``,
  ``FallRedemptionRecord``, ``CompromiseActType.feeding_taint_role``: EMPTY IN
  PRODUCTION (0 rows; no feeding-taint act is authored). The copies are written
  anyway so a database with rows converts correctly.

Historical models only. The three name strings are a one-off translation of the old
enum values and are deliberately local to this file.
"""

from decimal import Decimal

from django.db import migrations

_VALUE_TO_NAME = {
    "celestial": "Celestial",
    "primal": "Primal",
    "abyssal": "Abyssal",
}

# (config column, from, to, conversion type, model default)
_CONVERSIONS = (
    ("celestial_to_primal_multiplier", "Celestial", "Primal", "FALL", Decimal("1.20")),
    ("celestial_to_abyssal_multiplier", "Celestial", "Abyssal", "FALL", Decimal("1.50")),
    ("primal_to_abyssal_multiplier", "Primal", "Abyssal", "FALL", Decimal("1.20")),
    ("abyssal_to_primal_multiplier", "Abyssal", "Primal", "REDEMPTION", Decimal("0.70")),
    ("primal_to_celestial_multiplier", "Primal", "Celestial", "REDEMPTION", Decimal("0.70")),
    ("abyssal_to_celestial_multiplier", "Abyssal", "Celestial", "REDEMPTION", Decimal("0.50")),
)

# (config column, affinity name, model default)
_COEFFICIENTS = (
    ("celestial_coefficient", "Celestial", 0),
    ("primal_coefficient", "Primal", 2),
    ("abyssal_coefficient", "Abyssal", 10),
)

_FEEDING_ROLES = {
    "Murder by Anima Drain": "murder",
    "Seduction Feeding - Deception": "seduction_deception",
    "Seduction Feeding - Predation": "seduction_predation",
}

# (model, old CharField, new FK)
_REF_COPIES = (
    ("CombatOpponent", "affinity", "affinity_ref"),
    ("AuraAffinityThreshold", "affinity", "affinity_ref"),
    ("ResonanceConversion", "target_affinity", "target_affinity_ref"),
    ("FallRedemptionRecord", "from_affinity", "from_affinity_ref"),
    ("FallRedemptionRecord", "to_affinity", "to_affinity_ref"),
    ("VowSituationalPerkSituation", "affinity", "affinity_ref"),
    ("VowSituationalPerkRung", "affinity", "affinity_ref"),
    ("VowAddedEffect", "affinity", "affinity_ref"),
)


def _affinity_rows(apps):
    affinity_model = apps.get_model("arxii", "Affinity")
    rows = {a.name: a for a in affinity_model.objects.filter(name__in=_VALUE_TO_NAME.values())}
    missing = sorted(set(_VALUE_TO_NAME.values()) - set(rows))
    if missing:
        msg = f"Affinity rows missing for the backfill: {', '.join(missing)}"
        raise RuntimeError(msg)
    return rows


def _row_for(rows, value, where):
    name = _VALUE_TO_NAME.get(value)
    if name is None:
        msg = f"{where}: affinity value {value!r} has no Affinity row"
        raise RuntimeError(msg)
    return rows[name]


def _config_value(config, column, default):
    return getattr(config, column) if config is not None else default


def _write_conversions(apps, rows):
    config = apps.get_model("arxii", "FallRedemptionConfig").objects.order_by("pk").first()
    interaction_model = apps.get_model("arxii", "AffinityInteraction")
    for column, src, dst, kind, default in _CONVERSIONS:
        updated = interaction_model.objects.filter(
            source_affinity=rows[src], environment_affinity=rows[dst]
        ).update(conversion_multiplier=_config_value(config, column, default), conversion_type=kind)
        if updated != 1:
            msg = f"AffinityInteraction {src} -> {dst}: expected exactly 1 row, found {updated}"
            raise RuntimeError(msg)


def _write_coefficients(apps, rows):
    config = apps.get_model("arxii", "CorruptionConfig").objects.order_by("pk").first()
    for column, name, default in _COEFFICIENTS:
        rows[name].corruption_coefficient = _config_value(config, column, default)
        rows[name].save(update_fields=["corruption_coefficient"])


def _copy_refs(apps, rows):
    for model_name, old, new in _REF_COPIES:
        model = apps.get_model("arxii", model_name)
        for value, name in _VALUE_TO_NAME.items():
            model.objects.filter(**{old: value, f"{new}__isnull": True}).update(**{new: rows[name]})
        stray = model.objects.exclude(**{old: ""}).filter(**{f"{new}__isnull": True}).first()
        if stray is not None:
            _row_for(rows, getattr(stray, old), f"{model_name}.{old}")


def _copy_auras(apps, rows):
    aura_model = apps.get_model("arxii", "CharacterAura")
    share_model = apps.get_model("arxii", "CharacterAuraShare")
    existing = set(share_model.objects.values_list("aura_id", "affinity_id"))
    shares = [
        share_model(aura=aura, affinity=rows[name], percent=getattr(aura, value))
        for aura in aura_model.objects.all()
        for value, name in _VALUE_TO_NAME.items()
        if (aura.pk, rows[name].pk) not in existing
    ]
    share_model.objects.bulk_create(shares)


def _set_feeding_roles(apps):
    act_model = apps.get_model("arxii", "CompromiseActType")
    for name, role in _FEEDING_ROLES.items():
        act_model.objects.filter(name=name, feeding_taint_role="").update(feeding_taint_role=role)


def forwards(apps, schema_editor):
    if not apps.get_model("arxii", "Affinity").objects.exists():
        # Fresh database (empty migrate, clone, regeneration gate): nothing to convert.
        return
    rows = _affinity_rows(apps)
    _write_conversions(apps, rows)
    _write_coefficients(apps, rows)
    _copy_refs(apps, rows)
    _copy_auras(apps, rows)
    _set_feeding_roles(apps)


def backwards(apps, schema_editor):
    """Clear the shares, conversions, coefficients, roles and _ref FKs.

    Broader than what forwards wrote, which is acceptable: rolling back 0302 drops
    these columns and the share table anyway, and the old CharFields keep the source.
    """
    apps.get_model("arxii", "CharacterAuraShare").objects.all().delete()
    apps.get_model("arxii", "AffinityInteraction").objects.update(
        conversion_multiplier=None, conversion_type=""
    )
    apps.get_model("arxii", "Affinity").objects.update(corruption_coefficient=0)
    apps.get_model("arxii", "CompromiseActType").objects.update(feeding_taint_role="")
    for model_name, _old, new in _REF_COPIES:
        apps.get_model("arxii", model_name).objects.update(**{new: None})


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0302_characteraurashare_affinity_corruption_coefficient_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
