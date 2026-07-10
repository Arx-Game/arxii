"""Communication-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetFilters, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location, send_message
from world.gm.constants import GMLevel
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import record_interaction, record_whisper_interaction

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona, Scene


# Module-level filter constants used as dataclass defaults (RUF009: no calls in defaults).
# TargetFilters is frozen, so sharing a single instance is safe.
_WHISPER_TARGET_FILTERS = TargetFilters(in_same_scene=True, exclude_self=True)


def _characters_to_active_personas(characters: list[ObjectDB]) -> list[Persona] | None:
    """Resolve character objects to their active personas.

    Returns None if no characters could be resolved (callers treat None as
    'no explicit targets'). Thin alias over the shared
    ``world.scenes.interaction_services.personas_for_characters`` helper — the
    REST submit-pose path (#2156) resolves directed-pose targets through the
    same function, so both surfaces derive InteractionTargetPersona rows identically.
    """
    from world.scenes.interaction_services import personas_for_characters  # noqa: PLC0415

    return personas_for_characters(characters)


def _flag_blocked_contact_for_targets(
    actor: ObjectDB,
    targets: list[ObjectDB],
    *,
    scene: Scene | None = None,
) -> None:
    """Fire BlockContactFlag for any blocked-pair contact in a communication action (#1278).

    Resolves the actor's and each target's active persona, then calls
    ``flag_blocked_contact_attempt``. The service is a no-op when no active block
    exists (target did not block the initiator), and dedupes per (blocker, blocked,
    scene) — so calling it unconditionally is safe. Zero signal to either player.
    """
    try:
        initiator_persona = actor.sheet_data.primary_persona
    except (AttributeError, ObjectDoesNotExist):
        return
    if initiator_persona is None:
        return
    from world.scenes.block_services import flag_blocked_contact_attempt  # noqa: PLC0415

    for target in targets:
        try:
            target_persona = target.sheet_data.primary_persona
        except (AttributeError, ObjectDoesNotExist):
            continue
        if target_persona is not None:
            flag_blocked_contact_attempt(
                initiator_persona=initiator_persona,
                target_persona=target_persona,
                scene=scene,
            )


def _active_scene_for(actor: ObjectDB) -> Scene | None:
    """Resolve the active scene at the actor's location, if any."""
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    return get_active_scene(actor.location)


@dataclass
class SayAction(Action):
    """Say something to the room."""

    key: str = "say"
    name: str = "Say"
    icon: str = "chat"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
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

        target_personas = _characters_to_active_personas(targets) if targets else None

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

        # #1278/#2088 — flag circumvention: a blocked player directing a say at the
        # blocker via another identity. Room-wide says (no targets) are already
        # handled by the visibility filter; only directed says are contact attempts.
        if targets:
            _flag_blocked_contact_for_targets(actor, targets, scene=_active_scene_for(actor))

        return ActionResult(success=True)


@dataclass
class PoseAction(Action):
    """Pose/emote to the room."""

    key: str = "pose"
    name: str = "Pose"
    icon: str = "theater"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
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

        target_personas = _characters_to_active_personas(targets) if targets else None

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

        # #1278/#2088 — flag circumvention: a blocked player directing a pose at the
        # blocker via another identity. Room-wide poses (no targets) are already
        # handled by the visibility filter; only directed poses are contact attempts.
        if targets:
            _flag_blocked_contact_for_targets(actor, targets, scene=_active_scene_for(actor))

        return ActionResult(success=True)


@dataclass
class EmitAction(Action):
    """Emit raw text to the room (no character name prepended).

    Classic MUSH emit: the text appears as-is in the scene feed. The interaction
    metadata still records who wrote it (persona, thumbnail, etc.), but the
    content itself has no automatic name prefix — the writer controls the
    entire text.
    """

    key: str = "emit"
    name: str = "Emit"
    icon: str = "scroll"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    intent_event: str | None = "before_emit"
    result_event: str | None = "emit"

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
            return ActionResult(success=False, message="Emit what?")

        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)

        target_personas = _characters_to_active_personas(targets) if targets else None

        # Broadcast raw text — no funcparser, no name prepend
        message_location(caller_state, text)
        record_interaction(
            character=actor,
            content=text,
            mode=InteractionMode.EMIT,
            target_personas=target_personas,
            place=place,
        )

        return ActionResult(success=True)


@dataclass
class MutterAction(Action):
    """Mutter to specific listeners; the room catches a fragment (#905).

    Receivers hear (and their feed records) the full text; everyone else
    in the room hears a random-word fragment — which is also what the
    public log shows, preserving the never-more-than-the-room-heard
    invariant. Risky by design: the wrong word can leak.
    """

    key: str = "mutter"
    name: str = "Mutter"
    icon: str = "whisper"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    intent_event: str | None = "before_mutter"
    result_event: str | None = "mutter"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.interaction_services import (  # noqa: PLC0415
            mutter_fragment,
            record_mutter_interaction,
        )

        text = kwargs.get("text", "")
        receivers: list[ObjectDB] = kwargs.get("receivers", [])
        if not text:
            return ActionResult(success=False, message="Mutter what?")
        if not receivers:
            return ActionResult(success=False, message="Mutter to whom?")

        sdm = context.scene_data if context else SceneDataManager()

        fragment = mutter_fragment(text)
        receiver_ids = {receiver.pk for receiver in receivers}
        # Telnet delivery: full text to receivers, fragment to the rest.
        for receiver in receivers:
            receiver_state = sdm.initialize_state_for_object(receiver)
            send_message(receiver_state, f'{actor.key} mutters, "{text}"')
        location = actor.location
        if location is not None:
            for obj in location.contents:
                if obj.pk in receiver_ids or obj.pk == actor.pk:
                    continue
                if not hasattr(obj, "msg"):
                    continue
                bystander_state = sdm.initialize_state_for_object(obj)
                send_message(bystander_state, f'{actor.key} mutters, "{fragment}"')

        record_mutter_interaction(character=actor, receivers=receivers, content=text)

        return ActionResult(success=True)


@dataclass
class PemitAction(Action):
    """STARTING-tier GM private narrative emit to an explicit receiver list (#906).

    The Arx 1 "pemit": GM narration delivered only to the listed characters.
    Rides the receiver-scoped EMIT path — the persisted interaction carries
    receiver rows, so the feed shows it only to those receivers (and the
    scene log never shows more than the room heard). Works inside scenes
    (record_interaction resolves the active scene from the room) and at
    room level outside scenes (persists scene-less), per the #906 ruling.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.STARTING)`` (#2117; staff
    bypass preserved) -- pure private narration, no state change beyond a
    receiver-scoped Interaction row, same risk class as staging.
    """

    key: str = "pemit"
    name: str = "Private Emit"
    icon: str = "scroll"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    intent_event: str | None = "before_pemit"
    result_event: str | None = "pemit"

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.STARTING)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        text = kwargs.get("text", "")
        receivers: list[ObjectDB] = kwargs.get("receivers", [])
        if not text:
            return ActionResult(success=False, message="Pemit what?")
        if not receivers:
            return ActionResult(success=False, message="Pemit to whom?")

        receiver_personas = _characters_to_active_personas(receivers)
        if receiver_personas is None:
            return ActionResult(success=False, message="No valid receivers found.")

        sdm = context.scene_data if context else SceneDataManager()

        # Direct delivery to each receiver only — never the whole room.
        for receiver in receivers:
            receiver_state = sdm.initialize_state_for_object(receiver)
            send_message(receiver_state, text)

        record_interaction(
            character=actor,
            content=text,
            mode=InteractionMode.EMIT,
            receivers=receiver_personas,
        )

        return ActionResult(success=True)


@dataclass
class WhisperAction(Action):
    """Whisper to a specific target."""

    key: str = "whisper"
    name: str = "Whisper"
    icon: str = "whisper"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = _WHISPER_TARGET_FILTERS

    intent_event: str | None = "before_whisper"
    result_event: str | None = "whisper"

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

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

        # #1278/#2088 — flag circumvention attempts: a blocked player whispering the
        # blocker via another identity. No-op when no active block exists.
        _flag_blocked_contact_for_targets(actor, [target], scene=_active_scene_for(actor))

        return ActionResult(success=True)
