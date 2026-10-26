"""A player character's movement budget inside a combat encounter (#4607).

A mortal covers one hop a round; a stronger mover covers more, up to a cap. The
hops spent this round live on ``CombatParticipant.hops_used`` and refill when the
next declaration phase opens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import MAX_HOPS_PER_ROUND, MOVEMENT_PER_HOP, ParticipantStatus
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatParticipant


def active_combat_participant(objectdb: ObjectDB) -> CombatParticipant | None:
    """The character's ACTIVE participant row in a live encounter in their room, or None.

    "Live" is any status but COMPLETED, so a round that is resolving or between
    rounds still counts. A character with no sheet, no room or no such row gets None.
    """
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    if objectdb.db_location_id is None:
        return None
    try:
        sheet = objectdb.sheet_data
    except AttributeError:
        # RelatedObjectDoesNotExist subclasses AttributeError: no sheet.
        return None
    return (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
            encounter__room_id=objectdb.db_location_id,
        )
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .select_related("encounter", "character_sheet")
        .order_by("-encounter_id")
        .first()
    )


def hops_for(sheet: CharacterSheet) -> int:
    """How many hops the character may take each round.

    A movement value of 0 or less (rooted) gives none. Above that, one hop per
    ``MOVEMENT_PER_HOP`` points, never fewer than one and never more than
    ``MAX_HOPS_PER_ROUND``.
    """
    from world.conditions.constants import FoundationalCapability  # noqa: PLC0415
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
    value = get_effective_capability_value(sheet, movement)
    if value <= 0:
        return 0
    return max(1, min(MAX_HOPS_PER_ROUND, value // MOVEMENT_PER_HOP))


def hops_left(participant: CombatParticipant) -> int:
    """Hops the participant has not yet spent this round."""
    return max(0, hops_for(participant.character_sheet) - participant.hops_used)


def spend_combat_hop(participant: CombatParticipant, hops: int = 1) -> None:
    """Record ``hops`` spent this round (a climb over a wall costs more than one, #4663)."""
    participant.hops_used += hops
    participant.save(update_fields=["hops_used"])
