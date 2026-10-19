"""The scene's cast list (#4418): naming a crowd and giving it a voice a Guide can play.

Thin web-only wrappers over ``world.combat.services.crowd_voice`` (``voice_crowd``,
``describe_crowd``); the services own the rules and raise ``CrowdVoiceError`` with a
player-safe message. A voice is then lent like any story NPC (``offer_npc``). Both
take a ``scene_id``: the GM's panel dispatches as whichever character the GM is
browsing as, so the scene is named, not read off where that character stands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite, RunsScenePrerequisite, resolve_gm_scene
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

NO_SUCH_CROWD_MESSAGE = "Those aren't opponents in this scene."


def _opponent_ids(value: Any) -> list[int] | None:
    """``opponent_ids`` as ints: a list from the web, or a comma-separated string."""
    if isinstance(value, str):
        value = [part for part in value.split(",") if part.strip()]
    if not isinstance(value, list | tuple):
        return None
    try:
        return [int(part) for part in value]
    except (TypeError, ValueError):
        return None


def _crowd_in_scene(actor: ObjectDB, kwargs: dict[str, Any]) -> list | None:
    """The named ``opponent_ids`` rows when every one is in the scene's encounters."""
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    scene = resolve_gm_scene(actor, kwargs)
    ids = _opponent_ids(kwargs.get("opponent_ids"))
    if scene is None or not ids:
        return None
    opponents = list(
        CombatOpponent.objects.filter(pk__in=ids, encounter__scene=scene)
        .select_related("encounter", "threat_pool", "voice_persona__character_sheet")
        .order_by("pk")
    )
    if len(opponents) != len(set(ids)):
        return None
    return opponents


@dataclass
class VoiceCrowdAction(Action):
    """The scene's GM gives a crowd of opponents a voice to pose as.

    Kwargs: ``opponent_ids`` (the crowd's ``CombatOpponent`` rows, all in one of
    this scene's encounters), ``name`` (the voice's name), ``scene_id`` (else the
    active scene where the actor stands).
    """

    key: str = "voice_crowd"
    name: str = "Give Crowd a Voice"
    icon: str = "users"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [RunsScenePrerequisite()]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415
        from world.combat.services.crowd_voice import (  # noqa: PLC0415
            CrowdVoiceError,
            voice_crowd,
        )

        account = actor.account or resolve_account_or_none(actor)
        if account is None:
            return ActionResult(success=False, message="No account is playing this character.")
        voice_name = (kwargs.get("name") or "").strip()
        if not voice_name:
            return ActionResult(success=False, message="Name the crowd.")
        opponents = _crowd_in_scene(actor, kwargs)
        if opponents is None:
            return ActionResult(success=False, message=NO_SUCH_CROWD_MESSAGE)
        try:
            persona = voice_crowd(opponents=opponents, name=voice_name, by=account)
        except CrowdVoiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{persona.name} has a voice.",
            data={
                "persona_id": persona.pk,
                "roster_entry_id": persona.character_sheet.roster_entry.pk,
            },
        )


@dataclass
class DescribeCrowdAction(Action):
    """The scene's GM names and describes a crowd of opponents, all its rows at once.

    Kwargs: ``opponent_ids``, ``name``, ``description`` (either may be blank to keep
    it), ``scene_id`` (else the active scene where the actor stands). A voiced crowd's
    voice takes the new name too.
    """

    key: str = "describe_crowd"
    name: str = "Describe Crowd"
    icon: str = "users"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [RunsScenePrerequisite()]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.combat.services.crowd_voice import (  # noqa: PLC0415
            CrowdVoiceError,
            describe_crowd,
        )

        new_name = (kwargs.get("name") or "").strip()
        description = (kwargs.get("description") or "").strip()
        if not new_name and not description:
            return ActionResult(success=False, message="Give the crowd a name or a description.")
        opponents = _crowd_in_scene(actor, kwargs)
        if opponents is None:
            return ActionResult(success=False, message=NO_SUCH_CROWD_MESSAGE)
        try:
            describe_crowd(opponents=opponents, name=new_name, description=description)
        except CrowdVoiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        shown = new_name or opponents[0].name
        return ActionResult(
            success=True,
            message=f"The crowd is now {shown}.",
            data={"opponent_ids": [opponent.pk for opponent in opponents]},
        )


@dataclass
class PlaceNPCInSceneAction(Action):
    """The scene's GM puts one of their story NPCs into the scene's room.

    Kwargs: ``roster_entry_id``, ``scene_id``. The NPC then shows on the cast list.
    """

    key: str = "place_npc_in_scene"
    name: str = "Place NPC in Scene"
    icon: str = "user-plus"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [RunsScenePrerequisite()]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415
        from world.roster.models import RosterEntry  # noqa: PLC0415
        from world.roster.services.npc_placement import (  # noqa: PLC0415
            NPCPlacementError,
            place_npc_in_scene,
        )

        account = actor.account or resolve_account_or_none(actor)
        if account is None:
            return ActionResult(success=False, message="No account is playing this character.")
        scene = resolve_gm_scene(actor, kwargs)
        if scene is None:
            return ActionResult(success=False, message="There is no scene here.")
        try:
            entry_id = int(kwargs.get("roster_entry_id"))
        except (TypeError, ValueError):
            entry_id = None
        entry = (
            RosterEntry.objects.filter(pk=entry_id)
            .select_related("roster", "character_sheet__character")
            .first()
            if entry_id is not None
            else None
        )
        if entry is None:
            return ActionResult(success=False, message="No such NPC.")
        try:
            place_npc_in_scene(entry=entry, scene=scene, by=account)
        except NPCPlacementError as exc:
            return ActionResult(success=False, message=exc.user_message)
        name = entry.character_sheet.character.db_key
        return ActionResult(
            success=True,
            message=f"{name} is in {scene.name}.",
            data={"roster_entry_id": entry.pk},
        )
