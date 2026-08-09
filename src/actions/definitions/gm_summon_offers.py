"""GM summon consent responses — target-side accept/decline (#3071).

``SummonPlayerAction`` (``actions/definitions/gm_adjudication.py``) creates the
pending ``GMSummonOffer``; these two actions are the target's own responses to
it, mirroring the challenger/challenged shape of ``AcceptChallengeAction`` /
``DeclineChallengeAction`` (``actions/definitions/duels.py``) but for a simpler
one-shot GM->player prompt (row existence IS pending status — see the
``GMSummonOffer`` model docstring). No prerequisites beyond holding a character
sheet: a player always gets to decide their own consent, regardless of who
summoned them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.gm.models import GMSummonOffer


def _sheet(actor: ObjectDB) -> CharacterSheet | None:
    """Return *actor*'s CharacterSheet, or None if absent."""
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _pending_offer_for(actor: ObjectDB) -> GMSummonOffer | None:
    """Return *actor*'s own pending ``GMSummonOffer``, or ``None``."""
    from world.gm.models import GMSummonOffer  # noqa: PLC0415

    actor_sheet = _sheet(actor)
    if actor_sheet is None:
        return None
    return GMSummonOffer.objects.filter(target_sheet=actor_sheet).select_related("room").first()


@dataclass
class AcceptGMSummonAction(Action):
    """Accept a pending GM summon: move the actor to the GM's scene room (#3071)."""

    key: str = "accept_gm_summon"
    name: str = "Accept Summon"
    icon: str = "check"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        offer = _pending_offer_for(actor)
        if offer is None:
            return ActionResult(success=False, message="You have no pending summon to accept.")

        from world.gm.services import resolve_gm_summon_offer  # noqa: PLC0415

        room_name = offer.room.objectdb.db_key
        resolve_gm_summon_offer(offer, accept=True)

        return ActionResult(success=True, message=f"You are summoned to {room_name}.")


@dataclass
class DeclineGMSummonAction(Action):
    """Decline a pending GM summon: clear it without moving anyone (#3071)."""

    key: str = "decline_gm_summon"
    name: str = "Decline Summon"
    icon: str = "x"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        offer = _pending_offer_for(actor)
        if offer is None:
            return ActionResult(success=False, message="You have no pending summon to decline.")

        from world.gm.services import resolve_gm_summon_offer  # noqa: PLC0415

        resolve_gm_summon_offer(offer, accept=False)

        return ActionResult(success=True, message="You decline the summons.")
