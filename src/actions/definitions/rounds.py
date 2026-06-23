"""Opt-in round actions: start/join/leave/end a non-combat scene round (#520)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from world.scenes.constants import (
    ACTIVE_SCENE_ROUND_STATUSES,
    RoundStatus,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.models import SceneActionDeclaration, SceneRound, SceneRoundParticipant
from world.scenes.round_services import end_scene_round, resolve_scene_round, start_scene_round

# Repeated ActionResult failure messages, extracted to satisfy S1192.
NOT_IN_A_ROOM_MESSAGE = "You are not in a room."
NO_CHARACTER_SHEET_MESSAGE = "No character sheet found."

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


def _sheet(actor: ObjectDB) -> CharacterSheet | None:
    """Return the actor's CharacterSheet, or None if not present."""
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _active_round_for_room(room: ObjectDB) -> SceneRound | None:
    """Return the active (non-completed) SceneRound for a room, or None."""
    return SceneRound.objects.filter(room=room, status__in=ACTIVE_SCENE_ROUND_STATUSES).first()


@dataclass
class StartRoundAction(Action):
    """Start a non-combat round in the actor's current room.

    Reuses an existing active round if present; creates one otherwise.
    Advances a BETWEEN_ROUNDS round to DECLARING.
    """

    key: str = "start_round"
    name: str = "Start Round"
    icon: str = "clock"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sheet = _sheet(actor)
        room = actor.location

        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)
        if sheet is None:
            return ActionResult(success=False, message=NO_CHARACTER_SHEET_MESSAGE)

        rnd = _active_round_for_room(room)
        if rnd is None:
            rnd = SceneRound.objects.create(
                room=room,
                status=RoundStatus.DECLARING,
                round_number=1,
                start_reason=SceneRoundStartReason.OPT_IN,
            )
        elif rnd.status == RoundStatus.BETWEEN_ROUNDS:
            rnd = start_scene_round(rnd)

        SceneRoundParticipant.objects.get_or_create(
            scene_round=rnd,
            character_sheet=sheet,
        )
        return ActionResult(success=True, message="A round begins.")


@dataclass
class JoinRoundAction(Action):
    """Join an active round in the actor's current room."""

    key: str = "join_round"
    name: str = "Join Round"
    icon: str = "user-plus"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sheet = _sheet(actor)
        room = actor.location

        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)
        if sheet is None:
            return ActionResult(success=False, message=NO_CHARACTER_SHEET_MESSAGE)

        rnd = _active_round_for_room(room)
        if rnd is None:
            return ActionResult(success=False, message="There is no active round here.")

        SceneRoundParticipant.objects.get_or_create(
            scene_round=rnd,
            character_sheet=sheet,
        )
        return ActionResult(success=True, message="You join the round.")


@dataclass
class LeaveRoundAction(Action):
    """Leave the active round in the actor's current room."""

    key: str = "leave_round"
    name: str = "Leave Round"
    icon: str = "user-minus"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sheet = _sheet(actor)
        room = actor.location

        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)
        if sheet is None:
            return ActionResult(success=False, message=NO_CHARACTER_SHEET_MESSAGE)

        SceneRoundParticipant.objects.filter(
            scene_round__room=room,
            scene_round__status__in=ACTIVE_SCENE_ROUND_STATUSES,
            character_sheet=sheet,
        ).update(status=SceneRoundParticipantStatus.LEFT)

        return ActionResult(success=True, message="You leave the round.")


@dataclass
class EndRoundAction(Action):
    """End the active round in the actor's current room."""

    key: str = "end_round"
    name: str = "End Round"
    icon: str = "flag"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location

        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        rnd = _active_round_for_room(room)
        if rnd is None:
            return ActionResult(success=False, message="There is no active round here.")

        end_scene_round(rnd)
        return ActionResult(success=True, message="The round ends.")


@dataclass
class PassRoundAction(Action):
    """Pass for the current scene round — record an explicit no-action declaration.

    Costs a turn: dispatching this inside an active social round records the pass
    and lets ``dispatch_player_action`` drive presence-gated resolution. Do not
    resolve here.
    """

    key: str = "pass_round"
    name: str = "Pass"
    icon: str = "forward"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sheet = _sheet(actor)
        room = actor.location

        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)
        if sheet is None:
            return ActionResult(success=False, message=NO_CHARACTER_SHEET_MESSAGE)

        rnd = _active_round_for_room(room)
        if rnd is None:
            return ActionResult(success=False, message="There is no active round here.")
        if rnd.start_reason == SceneRoundStartReason.DANGER:
            return ActionResult(success=False, message="You cannot pass during a danger round.")

        participant = SceneRoundParticipant.objects.filter(
            scene_round=rnd,
            character_sheet=sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        ).first()
        if participant is None:
            return ActionResult(success=False, message="You are not in this round.")

        SceneActionDeclaration.objects.update_or_create(
            scene_round=rnd,
            round_number=rnd.round_number,
            participant=participant,
            is_immediate=False,
            defaults={
                "is_pass": True,
                "challenge_instance": None,
                "challenge_approach": None,
            },
        )
        return ActionResult(success=True, message="You pass.")


@dataclass
class ForceResolveRoundAction(Action):
    """Force the active round to resolve now, sweeping undeclared participants as passes.

    A GM meta-action, not a participant turn — ``costs_turn`` stays False. Ungated for
    now (consistent with start/end having no permission prerequisites in this foundation).
    """

    key: str = "force_resolve_round"
    name: str = "Force Resolve Round"
    icon: str = "fast-forward"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location

        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        rnd = _active_round_for_room(room)
        if rnd is None:
            return ActionResult(success=False, message="There is no active round here.")
        if rnd.start_reason == SceneRoundStartReason.DANGER:
            return ActionResult(success=False, message="A danger round resolves on its own.")

        if rnd.status != RoundStatus.DECLARING:
            return ActionResult(success=False, message="The round is not gathering declarations.")

        resolve_scene_round(rnd)
        return ActionResult(success=True, message="You force the round to resolve.")
