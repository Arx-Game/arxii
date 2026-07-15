"""Speaker queue Actions — thin wrappers over speaker_queue_services (#2356).

All REGISTRY backend, ``target_type=SELF``, ``category="scenes"``.
Shared by telnet ``CmdLine`` and the web ``SpeakerQueueViewSet``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType
from world.scenes.services import active_persona_for_sheet
from world.scenes.speaker_queue_services import (
    SpeakerQueueError,
    advance_queue,
    close_queue,
    get_active_queue,
    join_queue,
    leave_queue,
    open_queue,
    skip_speaker,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_NOT_IN_ROOM = "You are not in a room."
_NO_QUEUE = "There is no active speaker queue here."


def _broadcast_room_state(actor: ObjectDB) -> None:
    """Broadcast room state update to telnet clients in the room."""
    room = actor.location
    if room is not None:
        room._broadcast_room_state()  # noqa: SLF001


@dataclass
class OpenSpeakerQueueAction(Action):
    """Open a speaker queue in the actor's current room."""

    key: str = "open_speaker_queue"
    name: str = "Open Speaker Queue"
    icon: str = "list-plus"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location
        if room is None:
            return ActionResult(success=False, message=_NOT_IN_ROOM)
        persona = active_persona_for_sheet(actor.sheet_data)
        try:
            open_queue(room, persona)
        except SpeakerQueueError as exc:
            return ActionResult(success=False, message=exc.user_message)
        _broadcast_room_state(actor)
        return ActionResult(success=True, message="A speaker queue is now open.")


@dataclass
class CloseSpeakerQueueAction(Action):
    """Close the active speaker queue in the actor's room.

    Authority: the queue opener or a scene GM/staff.
    """

    key: str = "close_speaker_queue"
    name: str = "Close Speaker Queue"
    icon: str = "list-x"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location
        if room is None:
            return ActionResult(success=False, message=_NOT_IN_ROOM)
        queue = get_active_queue(room)
        if queue is None:
            return ActionResult(success=False, message=_NO_QUEUE)
        persona = active_persona_for_sheet(actor.sheet_data)
        is_staff = bool(actor.account and actor.account.is_staff)
        if not (queue.opened_by_id == persona.pk or is_staff):
            return ActionResult(
                success=False,
                message="Only the person who opened the queue or a GM may close it.",
            )
        close_queue(queue)
        _broadcast_room_state(actor)
        return ActionResult(success=True, message="The speaker queue is now closed.")


@dataclass
class JoinSpeakerQueueAction(Action):
    """Join the active speaker queue in the actor's room."""

    key: str = "join_speaker_queue"
    name: str = "Join Speaker Queue"
    icon: str = "list-end"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location
        if room is None:
            return ActionResult(success=False, message=_NOT_IN_ROOM)
        queue = get_active_queue(room)
        if queue is None:
            return ActionResult(success=False, message=_NO_QUEUE)
        persona = active_persona_for_sheet(actor.sheet_data)
        try:
            entry = join_queue(queue, persona)
        except SpeakerQueueError as exc:
            return ActionResult(success=False, message=exc.user_message)
        _broadcast_room_state(actor)
        return ActionResult(
            success=True,
            message=f"You are now in line at position {entry.position}.",
        )


@dataclass
class LeaveSpeakerQueueAction(Action):
    """Leave the active speaker queue in the actor's room."""

    key: str = "leave_speaker_queue"
    name: str = "Leave Speaker Queue"
    icon: str = "list-minus"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location
        if room is None:
            return ActionResult(success=False, message=_NOT_IN_ROOM)
        queue = get_active_queue(room)
        if queue is None:
            return ActionResult(success=False, message=_NO_QUEUE)
        persona = active_persona_for_sheet(actor.sheet_data)
        left = leave_queue(queue, persona)
        if not left:
            return ActionResult(success=False, message="You are not in line.")
        _broadcast_room_state(actor)
        return ActionResult(success=True, message="You leave the speaker queue.")


@dataclass
class AdvanceSpeakerQueueAction(Action):
    """Advance the speaker queue — remove current speaker, promote next.

    Authority: the current speaker (position 1), the queue opener, or a
    scene GM/staff. The opener's advance authority is independent of the
    current speaker's consent — it's the "keep things moving" escape valve.
    """

    key: str = "advance_speaker_queue"
    name: str = "Advance Speaker Queue"
    icon: str = "list-start"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location
        if room is None:
            return ActionResult(success=False, message=_NOT_IN_ROOM)
        queue = get_active_queue(room)
        if queue is None:
            return ActionResult(success=False, message=_NO_QUEUE)
        persona = active_persona_for_sheet(actor.sheet_data)
        is_staff = bool(actor.account and actor.account.is_staff)
        current = queue.entries.filter(position=1).first()
        is_current = current is not None and current.persona_id == persona.pk
        is_opener = queue.opened_by_id == persona.pk
        if not (is_current or is_opener or is_staff):
            return ActionResult(
                success=False,
                message="It is not your turn, and only the current speaker, the "
                "person who opened the queue, or a GM may advance it.",
            )
        next_entry = advance_queue(queue)
        _broadcast_room_state(actor)
        if next_entry is None:
            return ActionResult(success=True, message="The queue is now empty.")
        return ActionResult(
            success=True,
            message=f"The queue advances. {next_entry.persona.name} is now up.",
        )


@dataclass
class SkipSpeakerAction(Action):
    """Skip a specific persona from the speaker queue.

    Open to anyone — the AFK escape valve. Takes ``target_name`` kwarg.
    """

    key: str = "skip_speaker"
    name: str = "Skip Speaker"
    icon: str = "list-skip-forward"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room = actor.location
        if room is None:
            return ActionResult(success=False, message=_NOT_IN_ROOM)
        queue = get_active_queue(room)
        if queue is None:
            return ActionResult(success=False, message=_NO_QUEUE)
        target_name = kwargs.get("target_name", "")
        if not target_name:
            return ActionResult(success=False, message="Skip whom?")
        target = actor.search(target_name, global_search=False)
        if target is None:
            return ActionResult(success=False, message=f"No one named '{target_name}' here.")
        from world.scenes.models import Persona  # noqa: PLC0415

        target_persona = Persona.objects.filter(
            character_sheet__character=target,
        ).first()
        if target_persona is None:
            return ActionResult(success=False, message=f"{target_name} is not in line.")
        return _do_skip(actor, queue, target_name, target_persona)


def _do_skip(
    actor: ObjectDB,
    queue: Any,
    target_name: str,
    target_persona: Any,
) -> ActionResult:
    """Execute the skip and build the result message."""
    next_entry = skip_speaker(queue, target_persona)
    _broadcast_room_state(actor)
    if next_entry is not None:
        return ActionResult(
            success=True,
            message=f"{target_name} is skipped. {next_entry.persona.name} is now up.",
        )
    if queue.entries.exists():
        return ActionResult(success=True, message=f"{target_name} is skipped.")
    return ActionResult(
        success=True,
        message=f"{target_name} is skipped. The queue is now empty.",
    )
