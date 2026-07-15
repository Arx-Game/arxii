"""Service functions for the speaker queue — sole mutators (#2356).

Mirrors ``place_services.py``'s pattern: thin service functions that own
all queue mutations. Actions and the web ViewSet both call these.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from world.scenes.speaker_queue_models import SpeakerQueue, SpeakerQueueEntry

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona, Scene


_QUEUE_ALREADY_OPEN = "A speaker queue is already open here."
_ALREADY_IN_LINE = "You are already in line."


class SpeakerQueueError(Exception):
    """Expected failure in speaker queue operations."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def get_active_queue(room: ObjectDB) -> SpeakerQueue | None:
    """Return the active speaker queue for a room, or None."""
    return (
        SpeakerQueue.objects.filter(room=room, is_active=True)
        .select_related("opened_by", "scene")
        .first()
    )


def queue_entries(queue: SpeakerQueue) -> QuerySet[SpeakerQueueEntry]:
    """Return ordered entries for a queue with persona prefetched."""
    return queue.entries.select_related("persona").order_by("position")


def open_queue(room: ObjectDB, persona: Persona) -> SpeakerQueue:
    """Create an active speaker queue for the room.

    Args:
        room: The room to open the queue in.
        persona: The persona opening the queue.

    Returns:
        The new SpeakerQueue.

    Raises:
        SpeakerQueueError: If a queue is already active in this room.
    """
    from world.scenes.models import Scene  # noqa: PLC0415

    existing = get_active_queue(room)
    if existing is not None:
        raise SpeakerQueueError(_QUEUE_ALREADY_OPEN)

    scene = Scene.objects.active_for_room(room).first()
    return SpeakerQueue.objects.create(room=room, opened_by=persona, scene=scene)


def close_queue(queue: SpeakerQueue) -> None:
    """Close a speaker queue (soft-delete)."""
    queue.is_active = False
    queue.closed_at = timezone.now()
    queue.save(update_fields=["is_active", "closed_at"])


def join_queue(queue: SpeakerQueue, persona: Persona) -> SpeakerQueueEntry:
    """Add a persona to the end of the queue.

    Raises:
        SpeakerQueueError: If the persona is already in the queue.
    """
    if queue.entries.filter(persona=persona).exists():
        raise SpeakerQueueError(_ALREADY_IN_LINE)
    max_pos = queue.entries.count()
    return SpeakerQueueEntry.objects.create(
        speaker_queue=queue,
        persona=persona,
        position=max_pos + 1,
    )


def _renumber(queue: SpeakerQueue) -> None:
    """Renumber entries to be contiguous from 1."""
    entries = list(queue.entries.order_by("position"))
    for i, entry in enumerate(entries, start=1):
        if entry.position != i:
            entry.position = i
            entry.save(update_fields=["position"])


@transaction.atomic
def leave_queue(queue: SpeakerQueue, persona: Persona) -> bool:
    """Remove a persona from the queue and renumber.

    Returns:
        True if an entry was removed, False if the persona wasn't in the queue.
    """
    deleted, _ = queue.entries.filter(persona=persona).delete()
    if deleted:
        _renumber(queue)
        return True
    return False


@transaction.atomic
def advance_queue(queue: SpeakerQueue) -> SpeakerQueueEntry | None:
    """Remove the current speaker (position 1) and renumber.

    Returns:
        The new current speaker (position 1), or None if the queue is now empty.
    """
    current = queue.entries.filter(position=1).first()
    if current is None:
        return None
    current.delete()
    _renumber(queue)
    return queue.entries.filter(position=1).first()


@transaction.atomic
def skip_speaker(queue: SpeakerQueue, persona: Persona) -> SpeakerQueueEntry | None:
    """Remove a specific persona from the queue and renumber.

    Returns:
        The new current speaker if the removed persona was position 1, else None.
    """
    entry = queue.entries.filter(persona=persona).first()
    if entry is None:
        return None
    was_current = entry.position == 1
    entry.delete()
    _renumber(queue)
    if was_current:
        return queue.entries.filter(position=1).first()
    return None


def clear_queue_on_scene_finish(scene: Scene) -> None:
    """Close any active speaker queue for the scene's room.

    Called from ``finish_scene_full``. No-op if no active queue exists.
    """
    if scene.location is None:
        return
    queue = get_active_queue(scene.location)
    if queue is not None:
        close_queue(queue)


def remove_persona_from_room_queues(room: ObjectDB, persona: Persona) -> None:
    """Remove a persona from the room's active speaker queue.

    Called from departure/disconnect hooks. No-op if no active queue exists
    or the persona isn't in it.
    """
    queue = get_active_queue(room)
    if queue is None:
        return
    leave_queue(queue, persona)
