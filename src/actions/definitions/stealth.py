"""Sneak/unsneak — the mundane-stealth stance verbs (#3288).

``SneakAction`` rolls the SNEAK security oracle once for the current room and, on
success, applies sneak-sourced Concealed (#1225) via ``world.stealth.services``.
``UnsneakAction`` drops the stance with a public reveal. Shared by telnet
``CmdSneak`` (``src/commands/stealth.py``) and the web action dispatch.

Rulings (#3288): failure is silent to others and un-retryable in the same room
(one roll per room per visit); sneaking in place while observed names the
character in the echo (the room watched it happen); presence disclosure is
handled by the room_state ``has_unseen_presence`` flag + arrival echo, never
suppressed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_UNAVAILABLE_MESSAGE = "Stealth isn't available right now."


@dataclass
class SneakAction(Action):
    """Attempt to slip into the shadows — one concealment roll per room per visit."""

    key: str = "sneak"
    name: str = "Sneak"
    icon: str = "footprints"
    category: str = "movement"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    @staticmethod
    def _refusal_message(actor: ObjectDB) -> str | None:
        """Pre-roll gates: location, existing concealment, per-room token, seed."""
        from world.conditions.services import is_concealed  # noqa: PLC0415
        from world.stealth import services as stealth  # noqa: PLC0415

        if actor.location is None:
            return "There's nowhere to hide."
        if is_concealed(actor):
            return "You are already hidden."
        if stealth.room_already_rolled(actor):
            return (
                "PLACEHOLDER You've already tried to hide here; the room knows "
                "your tricks. Move on before trying again."
            )
        if stealth.concealed_template() is None:
            return _UNAVAILABLE_MESSAGE
        return None

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.stealth import services as stealth  # noqa: PLC0415

        refusal = self._refusal_message(actor)
        if refusal is not None:
            return ActionResult(success=False, message=refusal)

        stealth.mark_room_rolled(actor)
        try:
            check_result = stealth.roll_sneak(actor)
        except ValueError:
            return ActionResult(success=False, message=_UNAVAILABLE_MESSAGE)

        if check_result.success_level <= 0:
            # Silent failure (#3288 ruling): private message only, no room echo.
            return ActionResult(
                success=False,
                message="PLACEHOLDER You can't find a way out of sight here.",
            )

        if not stealth.start_sneaking(actor):
            return ActionResult(success=False, message=_UNAVAILABLE_MESSAGE)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        # In-place success names the character — the room just watched them do it.
        message_location(actor_state, "PLACEHOLDER $You() $conj(slip) into the shadows.")
        stealth.refresh_room_state(actor)
        return ActionResult(
            success=True,
            message=(
                "PLACEHOLDER You fade from sight. Everyone here can tell an unseen "
                "presence remains; who it is stays yours to keep."
            ),
        )


@dataclass
class UnsneakAction(Action):
    """Step out of the shadows deliberately, revealing your persona to the room."""

    key: str = "unsneak"
    name: str = "Unsneak"
    icon: str = "eye"
    category: str = "movement"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.stealth import services as stealth  # noqa: PLC0415

        if not stealth.stop_sneaking(actor):
            return ActionResult(success=False, message="You aren't hiding.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(actor_state, "PLACEHOLDER $You() $conj(step) out of the shadows.")
        stealth.refresh_room_state(actor)
        return ActionResult(success=True, message="PLACEHOLDER You reveal yourself.")
