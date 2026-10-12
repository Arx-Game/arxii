"""Resolving companion defeats at encounter end."""

from __future__ import annotations

from world.combat.constants import CombatAllegiance, OpponentStatus
from world.combat.models import CombatEncounter, CombatOpponent


def _resolve_companion_defeats(encounter: CombatEncounter) -> None:
    """Resolve each defeated bonded companion's stakes-gated consequence (#3652).

    #1873 Decision 4 put this at completion rather than at the defeat moment:
    all round resolution finishes before consequences resolve, and a DEFEATED
    companion is never re-targeted mid-resolution. Runs before
    cleanup_completed_encounter because the die outcome destroys the
    companion's ObjectDB, and the cleanup sweeps read opponent.objectdb.

    Skipped for ABANDONED by its caller: administrative closure is not a fight,
    and a GM ending a scene must not kill anyone's companion.
    """
    from world.companions.services import (  # noqa: PLC0415
        narrate_companion_loss,
        resolve_bonded_companion,
        resolve_companion_defeat,
    )

    opponents = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.DEFEATED,
        allegiance=CombatAllegiance.ALLY,
        summoned_by__isnull=False,
    ).select_related("objectdb")
    for opponent in opponents:
        companion = resolve_bonded_companion(opponent)
        if companion is None:
            continue
        name = companion.name
        if resolve_companion_defeat(companion, encounter.risk_level):
            narrate_companion_loss(name, encounter.scene)
