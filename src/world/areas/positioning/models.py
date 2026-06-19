from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.areas.positioning.constants import PositionKind


class PositionNodeBase(SharedMemoryModel):
    """Abstract base for position-node models (positioned tactical regions).

    Holds the shared descriptive fields. Concrete subclasses add their own
    FK anchor (e.g. ``room``) and any model-specific constraints.
    """

    name = models.CharField(max_length=50)
    kind = models.CharField(
        max_length=20, choices=PositionKind.choices, default=PositionKind.FEATURE
    )
    description = models.TextField(blank=True)

    class Meta:
        abstract = True


class PositionEdgeBase(SharedMemoryModel):
    """Abstract base for position-edge models (adjacency between two nodes).

    Holds ``is_passable`` and a shared canonical-order/self-loop validation
    helper. Concrete subclasses add their node FKs and call
    ``_validate_canonical`` from ``clean()``.
    """

    is_passable = models.BooleanField(default=True)

    class Meta:
        abstract = True

    @staticmethod
    def _validate_canonical(a_id: int | None, b_id: int | None) -> None:
        """Raise ValidationError if a_id == b_id or a_id > b_id.

        This covers the self-loop and canonical-order (pk-ascending) invariants
        shared by every edge type. Room-sameness checks are Position-specific
        and belong in the concrete subclass's ``clean()``.
        """
        if a_id is not None and b_id is not None:
            if a_id == b_id:
                msg = "An edge cannot connect a position to itself."
                raise ValidationError(msg)
            if a_id > b_id:
                msg = "position_a must have a lower id than position_b (canonical order)."
                raise ValidationError(msg)


class Position(PositionNodeBase):
    """A named tactical region within a room. The node of the positioning graph."""

    room = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE, related_name="positions")

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(fields=["room", "name"], name="unique_position_per_room"),
        ]
        ordering = ["room", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()}) in {self.room_id}"


class PositionEdge(PositionEdgeBase):
    """Traversable adjacency between two positions in the same room.

    Stored canonically (position_a_id < position_b_id). A non-null
    gating_challenge means crossing is gated by that Challenge (the
    cross-the-chasm gate); its approaches carry capability routes.
    """

    position_a = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="edges_as_a")
    position_b = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="edges_as_b")
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
                condition=Q(position_a__lt=F("position_b")), name="position_edge_canonical_order"
            ),
        ]
        ordering = ["position_a", "position_b"]

    def clean(self) -> None:
        super().clean()
        self._validate_canonical(self.position_a_id, self.position_b_id)
        if (
            self.position_a_id is not None
            and self.position_b_id is not None
            and self.position_a.room_id != self.position_b.room_id
        ):
            msg = "Both positions of an edge must be in the same room."
            raise ValidationError(msg)

    def __str__(self) -> str:
        return f"Edge({self.position_a_id}<->{self.position_b_id})"


class PositionBlueprint(SharedMemoryModel):
    """A reusable template of positions and edges, independent of any room.

    GMs author a blueprint once and apply it to any room, generating a
    live Position/PositionEdge graph from the template.
    """

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        app_label = "areas"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BlueprintPosition(PositionNodeBase):
    """A position node template that belongs to a PositionBlueprint.

    Mirrors ``Position`` but anchored to a blueprint rather than a room.
    """

    blueprint = models.ForeignKey(
        PositionBlueprint, on_delete=models.CASCADE, related_name="positions"
    )

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(
                fields=["blueprint", "name"], name="unique_blueprint_position_per_blueprint"
            ),
        ]
        ordering = ["blueprint", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()}) in blueprint:{self.blueprint_id}"


class BlueprintEdge(PositionEdgeBase):
    """Traversable adjacency between two BlueprintPositions in the same blueprint.

    Stored canonically (position_a_id < position_b_id). Mirrors ``PositionEdge``
    but targets blueprint nodes; the same-room check is replaced by a
    same-blueprint check.
    """

    blueprint = models.ForeignKey(PositionBlueprint, on_delete=models.CASCADE, related_name="edges")
    position_a = models.ForeignKey(
        BlueprintPosition, on_delete=models.CASCADE, related_name="edges_as_a"
    )
    position_b = models.ForeignKey(
        BlueprintPosition, on_delete=models.CASCADE, related_name="edges_as_b"
    )

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(
                fields=["position_a", "position_b"], name="unique_blueprint_edge"
            ),
            models.CheckConstraint(
                condition=Q(position_a__lt=F("position_b")),
                name="blueprint_edge_canonical_order",
            ),
        ]
        ordering = ["position_a", "position_b"]

    def clean(self) -> None:
        super().clean()
        self._validate_canonical(self.position_a_id, self.position_b_id)
        if (
            self.position_a_id is not None
            and self.position_b_id is not None
            and self.position_a.blueprint_id != self.position_b.blueprint_id
        ):
            msg = "Both positions of a blueprint edge must belong to the same blueprint."
            raise ValidationError(msg)

    def __str__(self) -> str:
        return f"BlueprintEdge({self.position_a_id}<->{self.position_b_id})"


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
