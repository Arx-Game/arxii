# Hand-written migration — rewrite min_giver_standing predicate leaves from
# `{giver: "<name>"}` to `{giver_id: <pk>}` so authored rule trees survive
# giver renames. Walks every predicate-tree JSONField in the missions app
# (MissionTemplate.availability_rule, MissionOption.visibility_rule,
# MissionGiverOffering.requirements_override) and rewrites in place.
#
# If a giver name can't be resolved (giver was deleted), the leaf is left
# as-is and a warning is printed — the rule was already broken (the runtime
# resolver would fail closed); the migration shouldn't claim to fix what it
# can't.
#
# Hand-written because `arx manage makemigrations` hangs on the Evennia
# superuser-creation wizard in this devcontainer.

from __future__ import annotations

from django.db import migrations

_LEAF_NAME = "min_giver_standing"
_OLD_PARAM = "giver"
_NEW_PARAM = "giver_id"

# Local copies of the Phase-0 evaluator's JSON-tree structural keys.
# Inlined (rather than imported from predicates.py) so this migration stays
# self-contained — apps/predicates.py is free to evolve in the future
# without breaking a long-applied historical migration.
_KEY_OP = "op"
_KEY_OF = "of"
_KEY_LEAF = "leaf"
_KEY_PARAMS = "params"


def _walk(node, giver_name_to_id, warnings):
    """Recursively rewrite predicate-tree nodes in place.

    Operates on the dict tree produced by the Phase 0 evaluator. Mutates
    `node` in place; returns nothing. AND/OR/NOT nodes recurse into their
    `of` operands. Leaf nodes with the target name + old param shape are
    rewritten to the new shape.
    """
    if not isinstance(node, dict) or not node:
        return
    if _KEY_OP in node:
        for child in node.get(_KEY_OF, []) or []:
            _walk(child, giver_name_to_id, warnings)
        return
    if node.get(_KEY_LEAF) != _LEAF_NAME:
        return
    params = node.get(_KEY_PARAMS) or {}
    if _OLD_PARAM not in params:
        return  # already migrated or never used the old shape
    name = params.pop(_OLD_PARAM)
    pk = giver_name_to_id.get(name)
    if pk is None:
        # Restore the param so we don't silently lose the broken reference;
        # the rule was already failing closed at runtime.
        params[_OLD_PARAM] = name
        warnings.append(name)
        return
    params[_NEW_PARAM] = pk
    node[_KEY_PARAMS] = params


def rewrite_predicate_givers(apps, schema_editor):
    MissionGiver = apps.get_model("missions", "MissionGiver")
    MissionTemplate = apps.get_model("missions", "MissionTemplate")
    MissionOption = apps.get_model("missions", "MissionOption")
    MissionGiverOffering = apps.get_model("missions", "MissionGiverOffering")

    giver_name_to_id = dict(MissionGiver.objects.values_list("name", "pk"))
    warnings: list[str] = []

    for tmpl in MissionTemplate.objects.exclude(availability_rule={}):
        original = tmpl.availability_rule
        _walk(original, giver_name_to_id, warnings)
        tmpl.availability_rule = original
        tmpl.save(update_fields=["availability_rule"])

    for opt in MissionOption.objects.exclude(visibility_rule={}):
        original = opt.visibility_rule
        _walk(original, giver_name_to_id, warnings)
        opt.visibility_rule = original
        opt.save(update_fields=["visibility_rule"])

    for offering in MissionGiverOffering.objects.exclude(requirements_override={}):
        original = offering.requirements_override
        _walk(original, giver_name_to_id, warnings)
        offering.requirements_override = original
        offering.save(update_fields=["requirements_override"])

    if warnings:
        unique = sorted(set(warnings))
        print(
            "0008_predicate_giver_name_to_id: "
            f"could not resolve {len(unique)} giver name(s) — "
            "rule(s) left in old shape (already broken at runtime): "
            f"{', '.join(unique)}"
        )


def noop_reverse(apps, schema_editor):
    """Reverse is a no-op: rewriting PKs back to names would require a
    snapshot of the original names, which we don't preserve. PKs are stable
    so this migration is one-way in practice."""


class Migration(migrations.Migration):
    dependencies = [
        ("missions", "0007_cooldown_min_value"),
    ]

    operations = [
        migrations.RunPython(rewrite_predicate_givers, noop_reverse),
    ]
