from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.areas.positioning.constants import PositionKind


class Position(SharedMemoryModel):
    """A named tactical region within a room. The node of the positioning graph."""

    room = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="positions"
    )
    name = models.CharField(max_length=50)
    kind = models.CharField(
        max_length=20, choices=PositionKind.choices, default=PositionKind.FEATURE
    )
    description = models.TextField(blank=True)

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(fields=["room", "name"], name="unique_position_per_room"),
        ]
        ordering = ["room", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()}) in {self.room_id}"


class PositionEdge(SharedMemoryModel):
    """Traversable adjacency between two positions in the same room.

    Stored canonically (position_a_id < position_b_id). A non-null
    gating_challenge means crossing is gated by that Challenge (the
    cross-the-chasm gate); its approaches carry capability routes.
    """

    position_a = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="edges_as_a")
    position_b = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="edges_as_b")
    is_passable = models.BooleanField(default=True)
    gating_challenge = models.ForeignKey(
        "mechanics.ChallengeInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gated_position_edges",
    )

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(
                fields=["position_a", "position_b"], name="unique_position_edge"
            ),
            models.CheckConstraint(
                check=Q(position_a__lt=F("position_b")), name="position_edge_canonical_order"
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.position_a_id == self.position_b_id:
            msg = "An edge cannot connect a position to itself."
            raise ValidationError(msg)
        if (
            self.position_a_id is not None
            and self.position_b_id is not None
            and self.position_a.room_id != self.position_b.room_id
        ):
            msg = "Both positions of an edge must be in the same room."
            raise ValidationError(msg)

    def __str__(self) -> str:
        return f"Edge({self.position_a_id}<->{self.position_b_id})"


class ObjectPosition(SharedMemoryModel):
    """Which Position an object currently occupies (OneToOne, like db_location).

    Invariant maintained by services: position.room == objectdb.db_location.
    """

    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="object_position",
    )
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="occupants")

    class Meta:
        app_label = "areas"

    def __str__(self) -> str:
        return f"{self.objectdb_id} @ {self.position_id}"
