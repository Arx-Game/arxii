"""The scene's cast list (#4418): giving a crowd a voice a Guide can play.

A thin web-only wrapper over ``world.combat.services.crowd_voice.voice_crowd``; the
service owns the rules and raises ``CrowdVoiceError`` with a player-safe message.
The voice is then lent like any story NPC (``offer_npc``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import IsSceneGMPrerequisite, Prerequisite
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


@dataclass
class VoiceCrowdAction(Action):
    """The scene's GM gives a crowd of opponents a voice to pose as.

    Kwargs: ``opponent_ids`` (the crowd's ``CombatOpponent`` rows, all in one of
    this scene's encounters), ``name`` (the voice's name).
    """

    key: str = "voice_crowd"
    name: str = "Give Crowd a Voice"
    icon: str = "users"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsSceneGMPrerequisite()]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415
        from world.combat.models import CombatOpponent  # noqa: PLC0415
        from world.combat.services.crowd_voice import (  # noqa: PLC0415
            CrowdVoiceError,
            voice_crowd,
        )
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        account = actor.account or resolve_account_or_none(actor)
        if account is None:
            return ActionResult(success=False, message="No account is playing this character.")
        voice_name = (kwargs.get("name") or "").strip()
        if not voice_name:
            return ActionResult(success=False, message="Name the crowd.")
        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message="There is no scene here.")
        ids = _opponent_ids(kwargs.get("opponent_ids"))
        if not ids:
            return ActionResult(success=False, message=NO_SUCH_CROWD_MESSAGE)
        opponents = list(
            CombatOpponent.objects.filter(pk__in=ids, encounter__scene=scene)
            .select_related("encounter", "threat_pool")
            .order_by("pk")
        )
        if len(opponents) != len(set(ids)):
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
