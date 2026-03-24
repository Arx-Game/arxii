"""Place and InteractionReceiver models for scene-scoped sub-locations."""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.scenes.constants import PlaceStatus


class Place(SharedMemoryModel):
    """A named sub-location within a room where characters can gather.

    Places let characters cluster into conversational groups within a
    single room. A tavern room might have "the bar", "corner booth",
    and "hearth" as places.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    room = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="places",
        help_text="The room this place belongs to",
    )
    status = models.CharField(
        max_length=20,
        choices=PlaceStatus.choices,
        default=PlaceStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "name"],
                condition=models.Q(room__isnull=False),
                name="unique_place_per_room",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class PlacePresence(SharedMemoryModel):
    """Tracks which persona is currently at a place."""

    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="presences",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="place_presences",
    )
    arrived_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["place", "persona"],
                name="unique_presence_per_place",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona.name} at {self.place.name}"


class InteractionReceiver(SharedMemoryModel):
    """Records exactly who received a place-scoped or targeted interaction.

    Replaces InteractionAudience for directed/place-scoped interactions.
    For public interactions (no place, no explicit receivers), no receiver
    rows are created -- everyone in the room can see them.
    """

    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.CASCADE,
        related_name="receivers",
        db_constraint=False,
        help_text="The interaction this receiver record belongs to",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction -- required for composite FK "
        "with partitioned table",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="interactions_received",
        help_text="The persona who received this interaction",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "persona"],
                name="unique_receiver_per_interaction",
            ),
        ]
        indexes = [
            models.Index(fields=["persona", "interaction"]),
            models.Index(
                fields=["timestamp"],
                name="interactionreceiver_ts_brin",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona.name} received interaction {self.interaction_id}"
