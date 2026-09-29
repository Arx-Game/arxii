"""The crown's actions (#4061 slice 2): call the underworld vote, cast your vote.

Thin over ``world.societies.crown``: the service owns the arithmetic and the
refusals (a majority of the city's criminal wards to call, a seat to vote);
these resolve the actor's persona, gate calling on organization leadership,
and turn a ``CrownError`` into the player-facing line.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


def _persona_for(actor: ObjectDB):
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = actor.character_sheet
    return sheet, (active_persona_for_sheet(sheet) if sheet is not None else None)


@dataclass
class CallCrownVoteAction(Action):
    """Call the city's crown vote for your organization (#4061).

    Kwargs: ``organization_id``, ``city_id``. Leadership-gated: only a
    leader-rank member of the organization may call in its name.
    """

    key: str = "call_crown_vote"
    name: str = "Call the Crown Vote"
    icon: str = "crown"
    category: str = "crime"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.models import Area  # noqa: PLC0415
        from world.societies.crown import CrownError, call_crown_vote  # noqa: PLC0415
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        _sheet, persona = _persona_for(actor)
        if persona is None:
            return ActionResult(success=False, message="You need a persona to call a vote.")
        organization = Organization.objects.filter(pk=kwargs.get("organization_id")).first()
        if organization is None:
            return ActionResult(success=False, message="Call the vote for which family?")
        city = Area.objects.filter(pk=kwargs.get("city_id")).first()
        if city is None:
            return ActionResult(success=False, message="Which city?")
        if not is_org_leader(persona, organization):
            return ActionResult(success=False, message=f"You do not speak for {organization.name}.")
        try:
            bid = call_crown_vote(organization, city, persona)
        except CrownError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"{organization.name} bids for the crown of {city.name}. The vote closes "
                f"{bid.closes_at:%Y-%m-%d}."
            ),
            data={"bid_id": bid.pk},
        )


@dataclass
class CastCrownVoteAction(Action):
    """Vote for or against the open bid, at the weight of your highest seat (#4061).

    Kwargs: ``bid_id``, ``in_favor`` (bool). Re-casting before the close
    replaces your vote. A staffer puppeting an NPC casts the NPC's vote.
    """

    key: str = "cast_crown_vote"
    name: str = "Cast Crown Vote"
    icon: str = "crown"
    category: str = "crime"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.crown import CrownError, cast_crown_vote  # noqa: PLC0415
        from world.societies.models import CrownBid  # noqa: PLC0415

        sheet, persona = _persona_for(actor)
        if sheet is None:
            return ActionResult(success=False, message="You need a character to vote.")
        bid = CrownBid.objects.filter(pk=kwargs.get("bid_id")).select_related("bidder").first()
        if bid is None:
            return ActionResult(success=False, message="No such vote.")
        try:
            vote = cast_crown_vote(bid, sheet, persona, in_favor=bool(kwargs.get("in_favor")))
        except CrownError as exc:
            return ActionResult(success=False, message=exc.user_message)
        side = "for" if vote.in_favor else "against"
        return ActionResult(
            success=True,
            message=f"You vote {side} {bid.bidder.name}, and your word carries {vote.weight}.",
            data={"vote_id": vote.pk, "weight": vote.weight},
        )
