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
from world.scenes.round_services import (
    RoundModeError,
    active_round_for_room,
    end_scene_round,
    resolve_scene_round,
    set_scene_round_mode,
    start_scene_round,
)

# Repeated ActionResult failure messages, extracted to satisfy S1192.
NOT_IN_A_ROOM_MESSAGE = "You are not in a room."
NO_CHARACTER_SHEET_MESSAGE = "No character sheet found."
NO_ACTIVE_ROUND_MESSAGE = "There is no active round here."

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
    return active_round_for_room(room)


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

    @staticmethod
    def _create_new_round(  # noqa: PLR0913
        actor: ObjectDB,
        room: ObjectDB,
        *,
        mode: str | None,
        advance_quorum_pct: int | None,
        max_actions_per_round: int | None,
        per_target_repeat_lock: bool | None,
    ) -> tuple[SceneRound | None, str | None]:
        """Create a fresh round; return (round, error_message).

        With no knob overrides, create a round from config defaults. With overrides,
        require an active scene and scene-admin permission, then apply the overrides.
        """
        from world.scenes.models import get_scene_round_defaults_config  # noqa: PLC0415

        cfg = get_scene_round_defaults_config()
        has_override = any(
            v is not None
            for v in (mode, advance_quorum_pct, max_actions_per_round, per_target_repeat_lock)
        )

        if not has_override:
            rnd = SceneRound.objects.create(
                room=room,
                status=RoundStatus.DECLARING,
                round_number=1,
                start_reason=SceneRoundStartReason.OPT_IN,
                mode=cfg.default_mode,
                advance_quorum_pct=cfg.advance_quorum_pct,
                max_actions_per_round=cfg.max_actions_per_round,
                per_target_repeat_lock=cfg.per_target_repeat_lock,
            )
            return rnd, None

        # Gate: overrides require an active scene + admin permission.
        from world.scenes.models import Scene as _Scene  # noqa: PLC0415
        from world.scenes.scene_admin_services import (  # noqa: PLC0415
            actor_can_administer_scene,
        )

        scene = _Scene.objects.filter(location=room, is_active=True).first()
        if scene is None or not actor_can_administer_scene(actor, scene):
            return None, (
                "Only a scene GM/owner can choose the round mode at start (start a scene first)."
            )

        rnd = SceneRound.objects.create(
            room=room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
            mode=mode if mode is not None else cfg.default_mode,
            advance_quorum_pct=(
                advance_quorum_pct if advance_quorum_pct is not None else cfg.advance_quorum_pct
            ),
            max_actions_per_round=(
                max_actions_per_round
                if max_actions_per_round is not None
                else cfg.max_actions_per_round
            ),
            per_target_repeat_lock=(
                per_target_repeat_lock
                if per_target_repeat_lock is not None
                else cfg.per_target_repeat_lock
            ),
            scene=scene,
        )
        return rnd, None

    def execute(  # noqa: PLR0913
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        mode: str | None = None,
        advance_quorum_pct: int | None = None,
        max_actions_per_round: int | None = None,
        per_target_repeat_lock: bool | None = None,
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
            rnd, error = self._create_new_round(
                actor,
                room,
                mode=mode,
                advance_quorum_pct=advance_quorum_pct,
                max_actions_per_round=max_actions_per_round,
                per_target_repeat_lock=per_target_repeat_lock,
            )
            if error is not None:
                return ActionResult(success=False, message=error)
        elif rnd.status == RoundStatus.BETWEEN_ROUNDS:
            rnd = start_scene_round(rnd)

        SceneRoundParticipant.objects.get_or_create(
            scene_round=rnd,
            character_sheet=sheet,
        )
        return ActionResult(success=True, message="A round begins.")


@dataclass
class SetRoundModeAction(Action):
    """Change the mode and/or knobs of the active scene round.

    Only the scene's GM or a co-owner may invoke this. A guard order applies:
    1. Actor must be in a room.
    2. The room must have an active scene (mode control requires scene context).
    3. The actor must be a scene admin (GM, staff, or co-owner).
    4. The room must have an active round to modify.
    5. The service validates the mode transition (DANGER immutable; STRICT-exit blocked by
       pending declarations).
    """

    key: str = "set_round_mode"
    name: str = "Set Round Mode"
    icon: str = "sliders"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(  # noqa: PLR0911, PLR0913
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        mode: str | None = None,
        advance_quorum_pct: int | None = None,
        max_actions_per_round: int | None = None,
        per_target_repeat_lock: bool | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.models import Scene as _Scene  # noqa: PLC0415
        from world.scenes.scene_admin_services import actor_can_administer_scene  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        scene = _Scene.objects.filter(location=room, is_active=True).first()
        if scene is None:
            return ActionResult(
                success=False,
                message="Mode ordering needs an active scene here — start one first.",
            )

        if not actor_can_administer_scene(actor, scene):
            return ActionResult(
                success=False,
                message="Only the scene's GM or an owner can set the round mode.",
            )

        rnd = _active_round_for_room(room)
        if rnd is None:
            return ActionResult(success=False, message=NO_ACTIVE_ROUND_MESSAGE)

        # Opportunistically link the round to the scene if not already linked.
        if rnd.scene_id is None:
            rnd.scene = scene
            rnd.save(update_fields=["scene"])

        try:
            set_scene_round_mode(
                rnd,
                mode=mode,
                advance_quorum_pct=advance_quorum_pct,
                max_actions_per_round=max_actions_per_round,
                per_target_repeat_lock=per_target_repeat_lock,
            )
        except RoundModeError as exc:
            return ActionResult(success=False, message=str(exc))

        if mode is not None:
            return ActionResult(success=True, message=f"Round mode set to {mode}.")
        return ActionResult(success=True, message="Round settings updated.")


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
            return ActionResult(success=False, message=NO_ACTIVE_ROUND_MESSAGE)

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
            return ActionResult(success=False, message=NO_ACTIVE_ROUND_MESSAGE)

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
            return ActionResult(success=False, message=NO_ACTIVE_ROUND_MESSAGE)

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
            return ActionResult(success=False, message=NO_ACTIVE_ROUND_MESSAGE)

        if rnd.status != RoundStatus.DECLARING:
            return ActionResult(success=False, message="The round is not gathering declarations.")

        resolve_scene_round(rnd)
        return ActionResult(success=True, message="You force the round to resolve.")


@dataclass
class SuccorSceneAction(Action):
    """Shelter a specific ally from environmental hazards in a non-combat scene round.

    The scene-round sibling of world.actions.definitions.combat_maneuvers.SuccorAction —
    wraps declare_succor_scene the same way that wraps declare_succor (#1744).
    """

    key: str = "scene_succor"
    name: str = "Succor"
    icon: str = "umbrella"
    category: str = "scene"
    target_type: TargetType = TargetType.SINGLE

    def execute(  # noqa: PLR0911 — distinct guard returns, each a specific failure message
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        ally_name: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.round_services import declare_succor_scene  # noqa: PLC0415

        room = actor.db_location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)
        scene_round = _active_round_for_room(room)
        if scene_round is None:
            return ActionResult(success=False, message=NO_ACTIVE_ROUND_MESSAGE)
        sheet = _sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=NO_CHARACTER_SHEET_MESSAGE)
        participant = SceneRoundParticipant.objects.filter(
            scene_round=scene_round,
            character_sheet=sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        ).first()
        if participant is None:
            return ActionResult(success=False, message="You are not an active participant here.")
        if not ally_name:
            return ActionResult(success=False, message="Succor requires an ally to shelter.")
        ally = SceneRoundParticipant.objects.filter(
            scene_round=scene_round,
            status=SceneRoundParticipantStatus.ACTIVE,
            character_sheet__character__db_key__iexact=ally_name,
        ).first()
        if ally is None:
            return ActionResult(success=False, message=f"No active ally named '{ally_name}' here.")
        try:
            declare_succor_scene(participant, ally)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You move to shelter your ally.")
