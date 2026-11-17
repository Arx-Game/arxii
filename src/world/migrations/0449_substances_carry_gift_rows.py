"""Carry each gift's substance row onto a shared ``Substance`` row (#5125). Data-only.

ADR-0237 disposition: restructure. ``GiftSubstance`` (one row per gift, naming the room
condition it works through) is replaced by ``Substance`` (one shared row per substance) and
``Gift.substance``. This migration copies what survives; a later migration removes
``GiftSubstance``.

* Rows group on ``(label trimmed and lower-cased, room condition, direction)``. Each group
  becomes one ``Substance`` named for its first label as written, and every major gift in the
  group points at it. A name already taken by a different reading becomes
  ``"<label> (<gift name>)"``, then a counter until it is free.
* ``property`` and the staff credit (``written_by`` and the other credit columns) come from the
  first row in the group that has one.
* A minor gift's row is skipped: a minor gift holds no substance. It is named in the summary.
* A major gift with no row of its own that has an ancestor with one takes that ancestor's
  substance, as the old lookup did.
* ``full_at``, ``opposed_by`` and ``arrival_line`` are deliberately discarded. The rulings of
  the spec replaced them (a place is rich in a substance by holding its Primum, an opposed
  substance is a relation row, and the call-up line is fixed), so there is nothing to carry.
* Call-up and scene-mark rows on the location cascade (source ``substance:<n>`` and
  ``scene_mark:<n>:<m>``) were transient and are deleted.
* The starter Primum steps and power curve are written only where a table holds no row at all,
  so staff rows are never overwritten and a second run adds nothing. The values are copied
  here, never imported: a migration is frozen.

# seed-data-ok: the starter Primum steps and power curve are the tuning rows a caster's power
# line cannot read without, written only into an empty table; the gift rows are a backfill.

It prints a summary (counts, merged names, skipped minor gifts, differing properties) so the
PR can list them.
"""

import sys

from django.db import migrations
from django.db.models import Q

SUBSTANCE_NAME_MAX = 60

#: ``GiftKind.MAJOR``, copied here because a migration is frozen.
MAJOR_GIFT_KIND = "MAJOR"

#: Source prefixes of the transient rows a call-up or a GM's mark wrote on the location cascade.
CALL_UP_SOURCE_PREFIXES = ("substance:", "scene_mark:")

#: ``(rank, name, starts_at, points)``, copied from the starter Primum steps.
STARTER_PRIMUM_STEPS = (
    (1, "Trace", 1, 2),
    (2, "Some", 10, 4),
    (3, "Rich", 30, 7),
    (4, "Massive", 100, 10),
)

#: ``(points_reached, power)``, copied from the starter power curve.
STARTER_POWER_CURVE = (
    (2, 2),
    (4, 4),
    (7, 6),
    (10, 8),
    (15, 10),
    (20, 11),
)


def _fit(label: str, suffix: str = "") -> str:
    """The label and suffix as one name no longer than a substance name may be."""
    return label[: SUBSTANCE_NAME_MAX - len(suffix)].rstrip() + suffix


def _free_substance(substance_model, label, stat_key, direction, gift_name):
    """The substance this reading is held by, as ``(row or None, name to create it under)``.

    A same-named row with the same reading is the one to reuse (a second run finds its own
    rows this way). A name taken by another reading gets the gift name appended, then a counter.
    """
    attempt = 0
    while True:
        if attempt == 0:
            name = _fit(label)
        elif attempt == 1:
            name = _fit(label, f" ({gift_name[:30]})")
        else:
            name = _fit(label, f" ({gift_name[:30]}) {attempt}")
        found = substance_model.objects.filter(name__iexact=name).first()
        if found is None:
            return None, name
        if (found.stat_key, found.direction) == (stat_key, direction):
            return found, found.name
        attempt += 1


def _group_rows(rows):
    """Group major gifts' rows by reading, in gift-name order; list the minor gifts' rows."""
    groups = {}
    skipped_minor = []
    for row in rows:
        if row.gift.kind != MAJOR_GIFT_KIND:
            skipped_minor.append(row.gift.name)
            continue
        key = (row.label.strip().lower(), row.stat_key, row.direction)
        groups.setdefault(key, []).append(row)
    return groups, skipped_minor


def _carry_groups(apps, groups, report):
    Substance = apps.get_model("arxii", "Substance")
    for (_label, stat_key, direction), group in groups.items():
        first = group[0]
        found, name = _free_substance(
            Substance, first.label.strip(), stat_key, direction, first.gift.name
        )
        if found is None:
            credited = next((r for r in group if r.written_by_id is not None), first)
            properties = [r.property for r in group if r.property_id is not None]
            found = Substance.objects.create(
                name=name,
                stat_key=stat_key,
                direction=direction,
                property=properties[0] if properties else None,
                written_by_id=credited.written_by_id,
                written_on=credited.written_on,
                reviewed_by_id=credited.reviewed_by_id,
                reviewed_on=credited.reviewed_on,
            )
            report["created"].append(name)
            distinct = sorted({p.name for p in properties})
            if len(distinct) > 1:
                report["properties"].append(f"{name}: kept {properties[0].name}; saw {distinct}")
        if len(group) > 1:
            report["merged"].append(f"{name}: {sorted(r.gift.name for r in group)}")
        for row in group:
            gift = row.gift
            if gift.substance_id is None:
                gift.substance = found
                gift.save(update_fields=["substance"])
                report["gifts"] += 1


def _carry_from_parents(apps, report):
    """A major gift with no substance of its own takes its nearest ancestor's."""
    Gift = apps.get_model("arxii", "Gift")
    by_pk = {gift.pk: gift for gift in Gift.objects.all()}
    for gift in by_pk.values():
        if gift.kind != MAJOR_GIFT_KIND or gift.substance_id is not None:
            continue
        seen = {gift.pk}
        parent = by_pk.get(gift.parent_id)
        while parent is not None and parent.pk not in seen:
            if parent.substance_id is not None:
                gift.substance_id = parent.substance_id
                gift.save(update_fields=["substance"])
                report["inherited"].append(gift.name)
                break
            seen.add(parent.pk)
            parent = by_pk.get(parent.parent_id)


def _delete_transient_rows(apps):
    LocationValueModifier = apps.get_model("arxii", "LocationValueModifier")
    query = Q()
    for prefix in CALL_UP_SOURCE_PREFIXES:
        query |= Q(source__startswith=prefix)
    deleted, _by_model = LocationValueModifier.objects.filter(query).delete()
    return deleted


def _insert_starter_tuning(apps):
    """Write the starter steps and curve into whichever table holds no row at all."""
    PrimumStep = apps.get_model("arxii", "PrimumStep")
    SubstancePowerStep = apps.get_model("arxii", "SubstancePowerStep")
    written = []
    if not PrimumStep.objects.exists():
        for rank, name, starts_at, points in STARTER_PRIMUM_STEPS:
            PrimumStep.objects.create(rank=rank, name=name, starts_at=starts_at, points=points)
        written.append(f"{len(STARTER_PRIMUM_STEPS)} Primum steps")
    if not SubstancePowerStep.objects.exists():
        for points_reached, power in STARTER_POWER_CURVE:
            SubstancePowerStep.objects.create(points_reached=points_reached, power=power)
        written.append(f"{len(STARTER_POWER_CURVE)} power steps")
    return written


def carry_gift_substances(apps, schema_editor) -> None:
    """Carry every ``GiftSubstance`` row onto ``Substance`` and ``Gift.substance``."""
    GiftSubstance = apps.get_model("arxii", "GiftSubstance")
    rows = list(GiftSubstance.objects.select_related("gift", "property").order_by("gift__name"))
    groups, skipped_minor = _group_rows(rows)
    report = {"created": [], "merged": [], "properties": [], "inherited": [], "gifts": 0}
    _carry_groups(apps, groups, report)
    _carry_from_parents(apps, report)
    deleted = _delete_transient_rows(apps)
    starter = _insert_starter_tuning(apps)

    lines = [
        f"substances carry: {len(rows)} gift rows, {len(report['created'])} substances created, "
        f"{report['gifts']} gifts set, {len(report['inherited'])} gifts took a parent's, "
        f"{deleted} transient call-up rows deleted, starter rows written: "
        f"{', '.join(starter) or 'none'}",
        f"  created: {report['created']}",
        f"  merged: {report['merged']}",
        f"  minor gifts skipped: {skipped_minor}",
        f"  differing properties: {report['properties']}",
        f"  took a parent's substance: {report['inherited']}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0448_gift_substance_major_only"),
    ]

    operations = [
        migrations.RunPython(carry_gift_substances, migrations.RunPython.noop),
    ]
