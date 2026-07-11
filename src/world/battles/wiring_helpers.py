"""Shared helpers for battle outcome-wiring modules (#2008).

Extracted from ``duel_wiring.py`` so both the Champion-duel outcome wiring and the
general party-encounter outcome wiring (``place_encounter_wiring.py``) call the
same rout logic instead of duplicating it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.battles.constants import BattleUnitStatus

if TYPE_CHECKING:
    from world.battles.models import BattlePlace

__all__ = ["rout_units_at_place"]


def rout_units_at_place(battle_place: BattlePlace, *, side_id: int) -> None:
    """Rout (or destroy, if already weak) every ACTIVE unit for *side_id* at *battle_place*.

    Preserves the existing severity rule byte-for-byte — a unit already at or below
    ROUTED_STRENGTH_THRESHOLD is wiped out when this fires, not merely routed — but
    expresses it through the numeric resources + the shared derivation (#1712)
    instead of writing ``status`` directly: status must always be a derived view, or
    a later ROUT/RALLY/STRIKE recomputing it for this unit would silently clobber a
    directly-written value.
    """
    from world.battles.constants import ROUTED_STRENGTH_THRESHOLD  # noqa: PLC0415
    from world.battles.models import BattleUnit  # noqa: PLC0415
    from world.battles.resolution import _compute_unit_status  # noqa: PLC0415

    units = BattleUnit.objects.filter(
        place=battle_place, side_id=side_id, status=BattleUnitStatus.ACTIVE
    )
    for unit in units:
        if unit.strength <= ROUTED_STRENGTH_THRESHOLD:
            unit.strength = 0
        unit.morale = 0
        unit.status = _compute_unit_status(unit.strength, unit.morale)
        unit.save(update_fields=["strength", "morale", "status"])
