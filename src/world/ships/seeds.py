"""Idempotent seed helpers for the ships system (#1832).

Per repo discipline (#683): seeds live in code, called via ``get_or_create``.
NOT a committed fixture.
"""

from __future__ import annotations

from world.buildings.models import BuildingKind
from world.ships.constants import SHIP_KIND_NAME


def ensure_ship_kind() -> BuildingKind:
    """Get-or-create the ``Vessel`` maritime ``BuildingKind`` row.

    Mirrors ``world.buildings.seeds.ensure_house_kind`` — a ship is a
    ``buildings.Building`` (maritime kind) decorated by ``ShipDetails``,
    not a separate hierarchy.
    """
    kind, _ = BuildingKind.objects.get_or_create(
        name=SHIP_KIND_NAME,
        defaults={
            "description": (
                "A seaworthy vessel. Constructed via a SHIP_CONSTRUCTION Project "
                "rather than the permit pipeline — see world.ships.services."
            ),
            "is_maritime": True,
        },
    )
    return kind
