"""Speaker queue models — a room-scoped turn-order utility for structured RP."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class SpeakerQueue(SharedMemoryModel):
    """A room-scoped speaker's queue — one active per room.

    A social coordination tool for structured gatherings (court, sermons,
    Q&A). Does NOT gate actions — players can pose/say/react freely
    regardless of queue state. Tracks whose turn it is for the spotlight.
    """

    room = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="speaker_queues",
        help_text="Room the queue belongs to.",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="speaker_queues",
        help_text="Active scene when the queue was opened, for auto-clear on scene finish.",
    )
    is_active = models.BooleanField(default=True)
    opened_by = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opened_speaker_queues",
        help_text="Persona who opened the queue.",
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room"],
                condition=models.Q(is_active=True),
                name="one_active_speaker_queue_per_room",
            ),
        ]

    def __str__(self) -> str:
        return f"SpeakerQueue(room={self.room_id}, active={self.is_active})"


class SpeakerQueueEntry(SharedMemoryModel):
    """An ordered entry in a speaker queue — one persona at one position."""

    speaker_queue = models.ForeignKey(
        SpeakerQueue,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="speaker_queue_entries",
    )
    position = models.PositiveIntegerField(
        help_text="Join-order: 1 = current speaker, 2 = next, etc.",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["speaker_queue", "persona"],
                name="unique_speaker_queue_entry_per_persona",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona.name} (pos {self.position}) in queue {self.speaker_queue_id}"
