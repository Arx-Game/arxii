"""LocationValueModifier helpers for Sanctum-grown resonance (Plan 4 §F).

Sanctum's grown resonance is stored as ``LocationValueModifier`` rows on
the Sanctum's ``RoomProfile`` tagged with ``source=f"sanctum:{pk}:homecoming"``
— NOT a field on ``SanctumDetails``. These helpers wrap the per-Sanctum
row management so callers (the Homecoming ritual, the Purging ritual,
the resonance cron tick) don't reach into the cascade model directly.

Per the revised spec, the cap (owner Path-level × 10 for Personal) applies
**only to Sanctum-source rows on this Sanctum** — authored ambient and
future spell/event-source rows on the same room are uncapped from Sanctum's
perspective. The cron tick reads the total via
``effective_value(room, resonance=type)`` (cascade-summed across all sources)
when computing per-weaver income.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum

from world.locations.models import LocationValueModifier
from world.locations.services import upsert_room_resonance_modifier

if TYPE_CHECKING:
    from world.magic.models import Resonance, SanctumDetails


def homecoming_source_tag(sanctum: SanctumDetails) -> str:
    """The ``LocationValueModifier.source`` value identifying this Sanctum's grown rows.

    Stable per Sanctum pk; never reused. Used both for ``get_or_create``
    lookups (Homecoming) and bulk filter+delete sweeps if a Sanctum is
    ever removed (future work — Sanctum has no bespoke decay today).
    """
    return f"sanctum:{sanctum.pk}:homecoming"


def sum_homecoming_value(sanctum: SanctumDetails) -> int:
    """Sum of all Homecoming-source row values for this Sanctum.

    Used for the cap-check inside Ritual of Homecoming (the cap applies
    only to this Sanctum's own grown rows; authored ambient + future
    sources are uncapped from Sanctum's perspective).
    """
    total = LocationValueModifier.objects.filter(
        source=homecoming_source_tag(sanctum),
    ).aggregate(total=Sum("value"))["total"]
    return total or 0


@transaction.atomic
def apply_homecoming_gain(sanctum: SanctumDetails, gain: int, cap: int) -> tuple[int, int]:
    """Apply ``gain`` to this Sanctum's Homecoming row, capping at ``cap``.

    Returns ``(applied, overflow)`` — how much landed in the row vs how
    much exceeded the per-Sanctum cap. Caller (Homecoming ritual) routes
    the overflow into ``SanctumDetails.pending_sacrifice_overflow``.

    Uses ``select_for_update`` on the existing row so concurrent
    Homecoming rituals on the same Sanctum serialize. Find-or-create
    fallback: if no row exists yet, create one with the gain value
    (clamped to cap).
    """
    if gain <= 0:
        return 0, 0

    current = sum_homecoming_value(sanctum)
    remaining = max(0, cap - current)
    applied = min(gain, remaining)
    overflow = gain - applied
    if applied == 0:
        return 0, overflow

    upsert_room_resonance_modifier(
        sanctum.feature_instance.room_profile,
        sanctum.resonance_type,
        source=homecoming_source_tag(sanctum),
        delta=applied,
    )
    return applied, overflow


@transaction.atomic
def drain_homecoming_for_purge(sanctum: SanctumDetails, retention_fraction: Decimal) -> None:
    """Multiply this Sanctum's Homecoming row values by ``retention_fraction``.

    Used by the Purging ritual — 0.5 retention means 50% is retained, the
    other half is destroyed (purging is intentionally costly per the spec).
    Walk the rows individually so SharedMemoryModel's identity map sees
    fresh values; bulk ``.update(...)`` would bypass it.
    """
    rows = LocationValueModifier.objects.select_for_update().filter(
        source=homecoming_source_tag(sanctum),
    )
    for row in rows:
        row.value = int(Decimal(row.value) * retention_fraction)
        row.save(update_fields=["value"])


@transaction.atomic
def retag_homecoming_for_new_resonance(sanctum: SanctumDetails, new_resonance: Resonance) -> None:
    """Switch this Sanctum's Homecoming rows to a new ``Resonance`` type.

    Used by the Purging ritual after the caller has changed
    ``sanctum.resonance_type``. Authored ambient + other sources on the
    same room are untouched — only the Sanctum's own homecoming-source
    rows adopt the new type. Walks the rows so SharedMemoryModel-cached
    instances see fresh resonance FKs.
    """
    rows = LocationValueModifier.objects.select_for_update().filter(
        source=homecoming_source_tag(sanctum),
    )
    for row in rows:
        row.resonance = new_resonance
        row.save(update_fields=["resonance"])
