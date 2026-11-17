"""Extracting Primum from a lair or a slain creature (#5125): the ``harvest_primum`` action.

The harvester names a substance, and for a slain creature the foe (``opponent_id``). The
service ``world.magic.services.harvest.harvest`` rolls the check and takes the Primum. A
substance she does not perceive, a dry lair and a harvested creature all answer in the same
words, so the answer never names Primum she has not sensed. The field-food ``harvest``
command is a different action and is not touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.magic.exceptions import HarvestNotConfigured

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.combat.models import CombatOpponent
    from world.magic.models import Substance


def _offered_substance(actor: ObjectDB, wanted: object) -> Substance | None:  # noqa: OBJECTDB_PARAM - the acting character
    """The substance named by name (any case) or pk, only among what the actor is offered.

    A substance she does not perceive is not among her offers, so a pk or a name for it
    behaves like an unknown one.
    """
    from world.magic.models import Substance  # noqa: PLC0415
    from world.magic.services.harvest import harvest_offers  # noqa: PLC0415

    text = str(wanted or "").strip().lower()
    if not text:
        return None
    for offer in harvest_offers(actor):
        if text == str(offer.substance_id) or text == offer.substance_name.lower():
            return Substance.objects.get(pk=offer.substance_id)
    return None


def _find_foe(actor: ObjectDB, opponent_id: object) -> CombatOpponent | None:  # noqa: OBJECTDB_PARAM - the acting character
    """The slain foe in the actor's room with this pk, or None."""
    from world.combat.constants import OpponentStatus  # noqa: PLC0415
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    if not str(opponent_id).isdigit():
        return None
    return CombatOpponent.objects.filter(
        pk=int(str(opponent_id)),
        encounter__room=actor.location,
        status=OpponentStatus.DEFEATED,
    ).first()


def _refresh_room_panels(actor: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM - the acting character
    """Push a fresh ``room_state`` to everyone here: what the place holds has changed.

    Each occupant's block is built for her own eyes, so a harvester's neighbour sees the lair
    drop a step only if she perceives it.
    """
    room = actor.location
    if room is None:
        return
    for occupant in room.sentient_contents:
        if hasattr(occupant, "send_room_state"):
            occupant.send_room_state()


@dataclass
class HarvestPrimumAction(Action):
    """Extract Primum of one substance from the lair she stands in or a slain creature."""

    key: str = "harvest_primum"
    name: str = "Extract Primum"
    icon: str = "flask-conical"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        substance: object = "",
        opponent_id: object = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.services.harvest import NOTHING_LEFT_MESSAGE, harvest  # noqa: PLC0415

        found = _offered_substance(actor, substance)
        foe = _find_foe(actor, opponent_id) if opponent_id not in (None, "") else None
        if found is None or (opponent_id not in (None, "") and foe is None):
            return ActionResult(success=False, message=NOTHING_LEFT_MESSAGE)
        try:
            result = harvest(actor, substance=found, opponent=foe)
        except HarvestNotConfigured as err:
            return ActionResult(success=False, message=err.user_message)
        if not result.harvested:
            return ActionResult(success=False, message=result.message)
        _refresh_room_panels(actor)
        if foe is not None:
            # The fight panel's offers come from the REST encounter; the same ping a round
            # sends makes every open panel refetch, so the harvested foe stops offering.
            from world.combat.services.encounter.state_ping import (  # noqa: PLC0415
                notify_encounter_changed_on_commit,
            )

            notify_encounter_changed_on_commit(foe.encounter)
        return ActionResult(
            success=True,
            message=result.message,
            data={
                "substance": result.substance_name,
                "amount_taken": result.amount_taken,
                "quantity": result.quantity,
                "outcome": result.outcome_name,
                "remaining_line": result.remaining_line,
            },
        )
