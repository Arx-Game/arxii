"""Scene lifecycle actions: start/finish a scene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError

# Re-use the same NOT_IN_A_ROOM_MESSAGE constant (defined in rounds.py and checked here).
NOT_IN_A_ROOM_MESSAGE = "You are not in a room."

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Scene


def _active_scene_for_room(room: ObjectDB) -> Scene | None:
    """Return the active RP Scene for a room, or None (excludes battle-backed scenes, #2010)."""
    from world.scenes.models import Scene as SceneModel  # noqa: PLC0415

    return SceneModel.objects.active_for_room(room).first()


@dataclass
class StartSceneAction(Action):
    """Start a scene in the actor's current room.

    If no active scene exists, creates one and grants co-ownership to every
    present PC with a controlling account.  If a scene is already active, the
    actor is recorded as a (non-owner) participant and informed.  Ungated.
    """

    key: str = "start_scene"
    name: str = "Start Scene"
    icon: str = "play"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.place_services import ensure_scene_for_location  # noqa: PLC0415
        from world.scenes.scene_admin_services import (  # noqa: PLC0415
            add_present_as_co_owners,
            enroll_present_table_gms,
            resolve_actor_account,
        )

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        scene = _active_scene_for_room(room)
        if scene is None:
            scene = ensure_scene_for_location(room)
            add_present_as_co_owners(scene, room)
            enroll_present_table_gms(scene, room)
            return ActionResult(success=True, message="A scene begins.")

        # Scene already exists — join the actor as a non-owner participant.
        account = resolve_actor_account(actor)
        if account is not None:
            from world.scenes.models import SceneParticipation  # noqa: PLC0415

            SceneParticipation.objects.get_or_create(
                scene=scene,
                account=account,
                defaults={"is_owner": False},
            )
        # A table-owning GM arriving after scene start still gets flagged (#2113).
        enroll_present_table_gms(scene, room)
        return ActionResult(success=True, message="A scene is already active here.")


@dataclass
class FinishSceneAction(Action):
    """Finish the active scene in the actor's current room.

    Gated: only the scene's GM, a co-owner, or a staff account may finish the
    scene.  Delegates to ``finish_scene_full`` for the full orchestration.
    """

    key: str = "finish_scene"
    name: str = "Finish Scene"
    icon: str = "stop-circle"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.scene_admin_services import (  # noqa: PLC0415
            actor_can_administer_scene,
            finish_scene_full,
            resolve_actor_account,
        )

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        scene = _active_scene_for_room(room)
        if scene is None:
            return ActionResult(success=False, message="There is no active scene here.")

        if not actor_can_administer_scene(actor, scene):
            return ActionResult(
                success=False,
                message="Only the scene's GM or an owner can finish the scene.",
            )

        finish_scene_full(scene, by_account=resolve_actor_account(actor))
        return ActionResult(success=True, message="The scene comes to a close.")


def _resolve_gm_grant_target(
    actor: ObjectDB,
    room: ObjectDB,
    target_name: str,
) -> tuple[CharacterSheet, AccountDB] | ActionResult:
    """Resolve + validate a ``scene gm <name>`` target.

    Returns ``(target_sheet, target_account)`` on success, or the failure
    ``ActionResult`` to return immediately. Extracted from ``execute()`` to keep
    its own return-statement count low (PLR0911), mirroring
    ``gm_combat.py``'s ``_validate_add_opponent_kwargs`` pattern.
    """
    from commands.utils.gm_resolution import resolve_character_sheet_in_room  # noqa: PLC0415
    from world.gm.models import GMProfile  # noqa: PLC0415
    from world.scenes.scene_admin_services import resolve_actor_account  # noqa: PLC0415

    target_name = target_name.strip()
    if not target_name:
        return ActionResult(success=False, message="Name a present character.")

    try:
        target_sheet = resolve_character_sheet_in_room(actor, target_name, room=room)
    except CommandError as err:
        return ActionResult(success=False, message=str(err))

    target_account = resolve_actor_account(target_sheet.character)
    if target_account is None:
        return ActionResult(
            success=False,
            message="That character has no controlling account.",
        )

    try:
        target_account.gm_profile  # noqa: B018 - side effect: triggers reverse lookup
    except GMProfile.DoesNotExist:
        return ActionResult(success=False, message="That account is not an approved GM.")

    return target_sheet, target_account


@dataclass
class GrantSceneGMAction(Action):
    """Explicitly grant ``is_gm`` to a present, approved GM account (#2113).

    The fallback for cases ``enroll_present_table_gms`` auto-detection can't reach
    (pickup games, guest players, an Assistant GM the scene owner wants to
    co-adjudicate). Gated: the actor must already administer the scene
    (``actor_can_administer_scene`` — is_gm / co-owner / staff / is_story_runner) and
    the target account must hold a ``GMProfile`` (any level — approval is itself the
    trust gate; no ``GMLevel`` tier check here).
    """

    key: str = "grant_scene_gm"
    name: str = "Grant Scene GM"
    icon: str = "shield"
    category: str = "scenes"
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.models import SceneParticipation  # noqa: PLC0415
        from world.scenes.scene_admin_services import actor_can_administer_scene  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        scene = _active_scene_for_room(room)
        if scene is None:
            return ActionResult(success=False, message="There is no active scene here.")

        if not actor_can_administer_scene(actor, scene):
            return ActionResult(
                success=False,
                message="Only the scene's GM or an owner can grant GM status.",
            )

        resolved = _resolve_gm_grant_target(actor, room, kwargs.get("target_name") or "")
        if isinstance(resolved, ActionResult):
            return resolved
        target_sheet, target_account = resolved

        SceneParticipation.objects.update_or_create(
            scene=scene,
            account=target_account,
            defaults={"is_gm": True},
        )
        return ActionResult(
            success=True,
            message=f"{target_sheet.character} is now a GM of this scene.",
        )


@dataclass
class MarkDecisiveCheckAction(Action):
    """Mark the next graded check in this scene as decisive for a beat (#1748).

    Creates a DecisiveCheckMarker (PENDING) and activates stakes contracts.
    When the next social check resolves, its CheckOutcome propagates to
    record_outcome_tier_completion — the same seam combat and missions use.

    Gated: the actor must administer the scene (actor_can_administer_scene).
    """

    key: str = "mark_decisive_check"
    name: str = "Mark Decisive Check"
    icon: str = "gavel"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.scene_admin_services import (  # noqa: PLC0415
            actor_can_administer_scene,
            resolve_actor_account,
        )

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=NOT_IN_A_ROOM_MESSAGE)

        scene = _active_scene_for_room(room)
        if scene is None:
            return ActionResult(success=False, message="There is no active scene here.")

        if not actor_can_administer_scene(actor, scene):
            return ActionResult(
                success=False,
                message="Only the scene's GM or an owner can mark a decisive check.",
            )

        if kwargs.get("cancel", False):
            return self._cancel_marker(scene)
        return self._create_marker(scene, actor, kwargs.get("beat_id"), resolve_actor_account)

    @staticmethod
    def _cancel_marker(scene: Scene) -> ActionResult:
        from world.scenes.decisive_check_services import (  # noqa: PLC0415
            DecisiveCheckError,
            cancel_decisive_check_marker,
            get_pending_marker,
        )

        marker = get_pending_marker(scene)
        if marker is None:
            return ActionResult(
                success=False,
                message="There is no pending decisive-check marker to cancel.",
            )
        try:
            cancel_decisive_check_marker(marker=marker)
        except DecisiveCheckError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Decisive-check marker cancelled.")

    @staticmethod
    def _create_marker(
        scene: Scene,
        actor: ObjectDB,
        beat_id: Any,
        resolve_account: Any,
    ) -> ActionResult:
        from world.scenes.decisive_check_services import (  # noqa: PLC0415
            DecisiveCheckError,
            create_decisive_check_marker,
        )
        from world.stories.models import Beat  # noqa: PLC0415

        if not beat_id:
            return ActionResult(success=False, message="Usage: scene decisive <beat-id>")

        try:
            beat = Beat.objects.get(pk=int(beat_id))
        except (Beat.DoesNotExist, ValueError, TypeError):
            return ActionResult(success=False, message=f"No beat found with id {beat_id}.")

        account = resolve_account(actor)
        try:
            create_decisive_check_marker(scene=scene, beat=beat, created_by=account)
        except DecisiveCheckError as exc:
            return ActionResult(success=False, message=exc.user_message)

        risk_label = beat.get_risk_display() if hasattr(beat, "get_risk_display") else beat.risk
        return ActionResult(
            success=True,
            message=(
                f"Decisive check marked for beat #{beat.pk} "
                f"(risk: {risk_label}). The next graded check in this scene "
                f"will resolve it."
            ),
        )
