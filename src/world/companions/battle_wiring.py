"""Battle-scale companion defeat consequence (#3652, #1873 Decision 4).

Mirrors world/ships/battle_wiring.py, the existing wired precedent for this
registry. The duel-scale twin lives in combat.services._resolve_companion_defeats;
both gate on their scale's risk_level, which is why #1873 Decision 4a added
Battle.risk_level.

DESTROYED is the authored predicate rather than an inference:
materialize_companion_as_battle_vehicle creates a non-structural vehicle, and
BattleVehicle.is_structural's own help text says non-structural destruction
reuses BattleUnitStatus.DESTROYED.
"""

from __future__ import annotations


def apply_companion_battle_outcome(battle) -> None:
    """Resolve each deployed companion whose vehicle was destroyed."""
    from world.battles.constants import BattleUnitStatus  # noqa: PLC0415
    from world.companions.models import CompanionDeployment  # noqa: PLC0415
    from world.companions.services import (  # noqa: PLC0415
        narrate_companion_loss,
        resolve_companion_defeat,
    )

    deployments = CompanionDeployment.objects.filter(battle=battle).select_related(
        "companion__owner__character", "vehicle__unit"
    )
    for deployment in deployments:
        if deployment.vehicle.unit.status != BattleUnitStatus.DESTROYED:
            continue
        companion = deployment.companion
        if companion.released_at is not None:
            continue
        name = companion.name
        owner_character = companion.owner.character
        if resolve_companion_defeat(companion, battle.risk_level):
            fallback_recipients = [owner_character] if owner_character is not None else []
            narrate_companion_loss(name, battle.scene, fallback_recipients=fallback_recipients)
