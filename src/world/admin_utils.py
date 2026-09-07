"""Shared Django admin helpers usable across every ``world`` sub-package (#3679).

A handful of hub models (``Resonance``, ``CapabilityType``, ``DamageType``, ...) are
referenced by FK/M2M from many unrelated apps. Hand-listing every consumer's
related_name in each admin goes stale the moment another app adds one more FK —
which is exactly how these models ended up admin-invisible in the first place.
``describe_reverse_relations`` instead derives the list from Django's own model
introspection, so it stays correct as new consumers are added.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

if TYPE_CHECKING:
    from django.db.models import Model


def describe_reverse_relations(obj: Model, *, exclude: frozenset[str] = frozenset()) -> str:
    """One entry per reverse FK/M2M/O2O relation on ``obj`` that has any rows.

    Read-only, admin-display use only — one query per relation (a handful, for the
    hub models this is built for), which is fine for a single detail-page render;
    do not call this from ``list_display`` (it is not prefetch-batched across rows).
    ``exclude`` names accessor names to skip (e.g. a relation already shown as its
    own inline or field elsewhere on the page).
    """
    if obj.pk is None:
        return "-"

    entries: list[str] = []
    for field in obj._meta.get_fields():  # noqa: SLF001
        if not (field.is_relation and field.auto_created and not field.concrete):
            continue
        accessor_name = field.get_accessor_name()
        if accessor_name in exclude:
            continue

        if field.one_to_one:
            try:
                related_obj = getattr(obj, accessor_name)
            except ObjectDoesNotExist:
                continue
            entries.append(f"{field.related_model._meta.verbose_name}: {related_obj}")  # noqa: SLF001
            continue

        count = getattr(obj, accessor_name).count()
        if not count:
            continue
        entries.append(f"{field.related_model._meta.verbose_name_plural}: {count}")  # noqa: SLF001

    return "; ".join(entries) if entries else "No connections found."
