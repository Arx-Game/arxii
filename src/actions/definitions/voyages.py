"""Voyage actions for the overworld travel system (#1855).

Four REGISTRY actions shared by telnet CmdVoyage and the web dispatcher:
- StartVoyageAction: set destination, compute route, create Voyage
- AdvanceLegAction: pay AP for next leg, move group to next hub (tempus fugit)
- CompleteVoyageAction: pay remaining AP, fast-forward to destination
- AbandonVoyageAction: end voyage at current hub
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionContext, ActionResult, TargetType
from world.travel.constants import VoyageStatus
from world.travel.models import Voyage, VoyageParticipant
from world.travel.services import (
    VoyageError,
    abandon_voyage,
    advance_leg,
    complete_voyage,
    start_voyage,
)


def _resolve_active_persona(actor: Any):
    """Resolve the actor's active Persona via sheet_data + active_persona_for_sheet."""
    try:
        sheet = actor.sheet_data
    except AttributeError:
        return None
    if sheet is None:
        return None
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    return active_persona_for_sheet(sheet)


def _get_active_voyage(persona) -> Voyage | None:
    """Find the active voyage (DRAFT or IN_TRANSIT) for a persona."""
    participant = (
        VoyageParticipant.objects.filter(
            persona=persona,
            left_at__isnull=True,
            voyage__status__in=[VoyageStatus.DRAFT, VoyageStatus.IN_TRANSIT],
        )
        .select_related("voyage")
        .first()
    )
    return participant.voyage if participant else None


@dataclass
class StartVoyageAction(Action):
    """Start a voyage to a destination hub."""

    key: str = "start_voyage"
    name: str = "Start Voyage"
    icon: str = "ship"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"destination_id"})

    def execute(  # noqa: C901, PLR0911
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        from world.travel.models import TravelHub, TravelMethod  # noqa: PLC0415

        destination_id = kwargs.get("destination_id")
        method_id = kwargs.get("travel_method_id")
        ship_id = kwargs.get("ship_id")

        if destination_id is None:
            return ActionResult(success=False, message="Travel to where?")

        if isinstance(destination_id, int):
            dest_room = ObjectDB.objects.filter(pk=destination_id).first()
        else:
            dest_room = destination_id

        if dest_room is None:
            return ActionResult(success=False, message="That destination doesn't exist.")

        try:
            dest_hub = TravelHub.objects.get(room_profile__objectdb=dest_room)
        except TravelHub.DoesNotExist:
            return ActionResult(success=False, message="That isn't a travel hub.")

        if method_id is None:
            return ActionResult(success=False, message="You need to specify a travel method.")

        try:
            travel_method = TravelMethod.objects.get(pk=method_id)
        except TravelMethod.DoesNotExist:
            return ActionResult(success=False, message="That travel method doesn't exist.")

        ship = None
        if ship_id is not None:
            from world.ships.models import ShipDetails  # noqa: PLC0415

            ship = ShipDetails.objects.filter(pk=ship_id).first()
            if ship is None:
                return ActionResult(success=False, message="That ship doesn't exist.")

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="You need an active persona to travel.")

        try:
            voyage = start_voyage(
                leader=persona,
                destination_hub=dest_hub,
                travel_method=travel_method,
                ship=ship,
            )
        except VoyageError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You set out for {dest_hub.name}.",
            data={"voyage_id": voyage.pk},
        )


@dataclass
class AdvanceLegAction(Action):
    """Advance to the next hub on your voyage (tempus fugit)."""

    key: str = "advance_voyage_leg"
    name: str = "Advance Voyage"
    icon: str = "arrow-right"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="You need an active persona to travel.")

        voyage = _get_active_voyage(persona)
        if voyage is None:
            return ActionResult(success=False, message="You aren't on a voyage.")

        try:
            advance_leg(voyage, caller=persona)
        except VoyageError as exc:
            return ActionResult(success=False, message=exc.user_message)

        voyage.refresh_from_db()
        if voyage.status == VoyageStatus.ARRIVED:
            return ActionResult(success=True, message="You have arrived at your destination.")

        return ActionResult(success=True, message="You continue on your journey.")


@dataclass
class CompleteVoyageAction(Action):
    """Fast-forward to your destination by paying all remaining AP."""

    key: str = "complete_voyage"
    name: str = "Complete Voyage"
    icon: str = "flag"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="You need an active persona to travel.")

        voyage = _get_active_voyage(persona)
        if voyage is None:
            return ActionResult(success=False, message="You aren't on a voyage.")

        try:
            complete_voyage(voyage, caller=persona)
        except VoyageError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, message="You arrive at your destination.")


@dataclass
class AbandonVoyageAction(Action):
    """Abandon your voyage and stay at the current hub."""

    key: str = "abandon_voyage"
    name: str = "Abandon Voyage"
    icon: str = "x"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="You need an active persona to travel.")

        voyage = _get_active_voyage(persona)
        if voyage is None:
            return ActionResult(success=False, message="You aren't on a voyage.")

        try:
            abandon_voyage(voyage, caller=persona)
        except VoyageError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, message="You end your journey here.")


@dataclass
class InviteToVoyageAction(Action):
    """Invite a co-located character to join your voyage."""

    key: str = "invite_to_voyage"
    name: str = "Invite to Voyage"
    icon: str = "user-plus"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.travel.services import invite_to_voyage  # noqa: PLC0415

        target_persona_id = kwargs.get("target_persona_id")
        if target_persona_id is None:
            return ActionResult(success=False, message="Invite whom?")

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="You need an active persona to travel.")

        voyage = _get_active_voyage(persona)
        if voyage is None:
            return ActionResult(success=False, message="You aren't on a voyage.")

        invitee = Persona.objects.filter(pk=target_persona_id).first()
        if invitee is None:
            return ActionResult(success=False, message="That person doesn't exist.")

        try:
            invite_to_voyage(voyage, persona, invitee)
        except VoyageError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, message=f"You invite {invitee} to join your voyage.")


@dataclass
class RespondVoyageInviteAction(Action):
    """Accept or decline a voyage invitation."""

    key: str = "respond_voyage_invite"
    name: str = "Respond to Voyage Invite"
    icon: str = "check"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.travel.models import VoyageInvite  # noqa: PLC0415
        from world.travel.services import respond_to_voyage_invite  # noqa: PLC0415

        invite_id = kwargs.get("invite_id")
        accept = kwargs.get("accept", False)

        if invite_id is None:
            return ActionResult(success=False, message="Which invitation?")

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="You need an active persona.")

        invite = VoyageInvite.objects.filter(pk=invite_id, target_persona=persona).first()
        if invite is None:
            return ActionResult(success=False, message="You have no such invitation.")

        decision = VoyageInvite.Response.ACCEPTED if accept else VoyageInvite.Response.DECLINED

        try:
            respond_to_voyage_invite(invite, decision)
        except VoyageError as exc:
            return ActionResult(success=False, message=exc.user_message)

        verb = "accepted" if accept else "declined"
        return ActionResult(success=True, message=f"You {verb} the voyage invitation.")


@dataclass
class DepartVoyageAction(Action):
    """Depart on your voyage with accepted party members."""

    key: str = "depart_voyage"
    name: str = "Depart Voyage"
    icon: str = "ship"
    category: str = "movement"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.travel.services import depart_voyage  # noqa: PLC0415

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="You need an active persona to travel.")

        voyage = _get_active_voyage(persona)
        if voyage is None:
            return ActionResult(success=False, message="You aren't on a voyage.")

        try:
            depart_voyage(voyage, caller=persona)
        except VoyageError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, message="You set out on your voyage.")
