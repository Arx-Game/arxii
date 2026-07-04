"""Battle-conclusion writeback: mark a deployed ship for repair (#1832 Task 7).

Registered as a ``world.battles.conclusion_hooks`` hook in
``world.ships.apps.ready()`` — ``battles`` stays free of any ``world.ships``
import (ADR-0010); this module is the one that reaches across the boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.battles.constants import FortificationKind
from world.battles.models import Fortification
from world.ships.models import ShipDeployment

if TYPE_CHECKING:
    from world.battles.models import Battle


def apply_ship_battle_outcome(battle: Battle) -> None:
    """Flag every deployed ship whose hull was breached as needing repair.

    For each ``ShipDeployment`` tied to ``battle``, checks the deployed
    vehicle's hull ``Fortification``; a breached hull sets
    ``ShipDetails.needs_repair`` so a ``SHIP_REPAIR`` Project can be started.
    """
    deployments = ShipDeployment.objects.filter(battle=battle).select_related(
        "ship", "vehicle__place"
    )
    for deployment in deployments:
        fortification = Fortification.objects.filter(
            place=deployment.vehicle.place, kind=FortificationKind.HULL
        ).first()
        if fortification is not None and fortification.breached:
            deployment.ship.needs_repair = True
            deployment.ship.save(update_fields=["needs_repair"])
