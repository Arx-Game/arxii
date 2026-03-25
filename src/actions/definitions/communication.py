"""Communication-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location, send_message
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import record_interaction, record_whisper_interaction

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona


def _resolve_target_personas(targets: list[ObjectDB]) -> list[Persona] | None:
    """Resolve character objects to their active personas.

    Returns None if no targets could be resolved (callers treat None as
    'no explicit targets').
    """
    personas: list[Persona] = []
    for target in targets:
        try:
            identity = target.character_identity
            if identity.active_persona:
                personas.append(identity.active_persona)
        except (AttributeError, ObjectDoesNotExist):
            continue
    return personas or None


@dataclass
class SayAction(Action):
    """Say something to the room."""

    key: str = "say"
    name: str = "Say"
    icon: str = "chat"
    category: str = "communication"
    target_type: TargetType = TargetType.AREA

    intent_event: str | None = "before_say"
    result_event: str | None = "say"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        text = kwargs.get("text", "")
        targets: list[ObjectDB] = kwargs.get("targets", [])
        if not text:
            return ActionResult(success=False, message="Say what?")

        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)

        target_personas = _resolve_target_personas(targets) if targets else None

        # Broadcast: raw text via Evennia msg_contents for telnet clients and
        # non-character objects. Web clients receive this as a TEXT message
        # but should prefer the structured INTERACTION payload from push_interaction.
        message_location(
            caller_state,
            f'$You() $conj(say) "{text}"',
        )
        # Record + push: creates DB record and sends structured WebSocket payload.
        # Web clients use this for the scene feed display.
        record_interaction(
            character=actor,
            content=text,
            mode=InteractionMode.SAY,
            target_personas=target_personas,
        )

        return ActionResult(success=True)


@dataclass
class PoseAction(Action):
    """Pose/emote to the room."""

    key: str = "pose"
    name: str = "Pose"
    icon: str = "theater"
    category: str = "communication"
    target_type: TargetType = TargetType.AREA

    intent_event: str | None = "before_pose"
    result_event: str | None = "pose"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        text = kwargs.get("text", "")
        targets: list[ObjectDB] = kwargs.get("targets", [])
        place = kwargs.get("place")
        if not text:
            return ActionResult(success=False, message="Pose what?")

        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)

        target_personas = _resolve_target_personas(targets) if targets else None

        # Broadcast: raw text via Evennia msg_contents for telnet clients and
        # non-character objects. Web clients receive this as a TEXT message
        # but should prefer the structured INTERACTION payload from push_interaction.
        message_location(caller_state, text)
        # Record + push: creates DB record and sends structured WebSocket payload.
        # Web clients use this for the scene feed display.
        record_interaction(
            character=actor,
            content=text,
            mode=InteractionMode.POSE,
            target_personas=target_personas,
            place=place,
        )

        return ActionResult(success=True)


@dataclass
class WhisperAction(Action):
    """Whisper to a specific target."""

    key: str = "whisper"
    name: str = "Whisper"
    icon: str = "whisper"
    category: str = "communication"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_whisper"
    result_event: str | None = "whisper"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        text = kwargs.get("text", "")
        if target is None or not text:
            return ActionResult(success=False, message="Whisper what to whom?")

        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        target_state = sdm.initialize_state_for_object(target)

        # Direct message: Evennia msg() to the target only, for telnet clients.
        # Web clients receive this as a TEXT message but should prefer the
        # structured INTERACTION payload from push_interaction.
        send_message(
            target_state,
            f'{caller_state.get_display_name(looker=target_state)} whispers "{text}"',
        )
        # Record + push: creates DB record and sends structured WebSocket payload.
        # Web clients use this for the scene feed display.
        record_whisper_interaction(character=actor, target=target, content=text)

        return ActionResult(success=True)
