from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
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
    elevation_anchor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elevated_over",
        help_text="The position immediately below this one (null = solid floor / bottom).",
    )

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
    blocks_flight = models.BooleanField(
        default=False,
        help_text="When true, the aerial mirror does NOT make this edge freely passable "
        "(anti-air ward): flight may not bypass it.",
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
    same-blueprint check. A non-null ``gating_challenge_template`` means
    ``instantiate_blueprint`` mints a live ``ChallengeInstance`` from it and
    gates the cloned ``PositionEdge`` (see ``instantiate_challenge`` in
    ``world.mechanics.challenge_resolution``).
    """

    blueprint = models.ForeignKey(PositionBlueprint, on_delete=models.CASCADE, related_name="edges")
    position_a = models.ForeignKey(
        BlueprintPosition, on_delete=models.CASCADE, related_name="edges_as_a"
    )
    position_b = models.ForeignKey(
        BlueprintPosition, on_delete=models.CASCADE, related_name="edges_as_b"
    )
    gating_challenge_template = models.ForeignKey(
        "mechanics.ChallengeTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
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


class PositionShelter(SharedMemoryModel):
    """Shelter against a hazard granted by a specific Position within a room.

    A local structural fact (tent, awning, rock overhang), not an ambient
    cascade value. Stacks additively with the room's cascade-resolved shelter
    and with other PositionShelter rows on the same position.

    Reuses the ``change_per_day`` / ``source`` / ``applied_at`` /
    ``current_value`` pattern from ``LocationValueModifier`` so a temporary
    ward can decay and a flow can clean up by source.
    """

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="shelters")
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        related_name="position_shelters",
    )
    value = models.IntegerField(
        help_text="Magnitude of shelter. Added to the room's cascade value."
    )
    change_per_day = models.IntegerField(
        default=0,
        help_text=(
            "Signed: negative decays toward zero, positive grows away from "
            "zero, zero is permanent. Mirrors LocationValueModifier."
        ),
    )
    source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Free-text label for cleanup (e.g. filter(source=...).delete()).",
    )
    applied_at = models.DateTimeField(
        default=timezone.now,
        help_text="Decay anchor. Update this to 'refresh' the modifier.",
    )

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(
                fields=["position", "damage_type", "source"],
                condition=~models.Q(source=""),
                name="unique_position_shelter_per_source",
            ),
        ]
        indexes = [
            models.Index(fields=["position", "damage_type"]),
        ]

    def current_value(self, *, now: datetime | None = None) -> int:
        """Return the lazy decay/growth-resolved value.

        Mirrors ``LocationValueModifier.current_value``. Returns 0 once the
        modifier has crossed its original sign. Partial days truncate toward
        zero.
        """
        if self.value == 0 or self.change_per_day == 0:
            return self.value
        anchor = now if now is not None else timezone.now()
        elapsed = anchor - self.applied_at
        days = elapsed.total_seconds() / 86400.0
        new_value = self.value + int(self.change_per_day * days)
        if self.value > 0 and new_value <= 0:
            return 0
        if self.value < 0 and new_value >= 0:
            return 0
        return new_value

    def __str__(self) -> str:
        return f"PositionShelter {self.damage_type_id}={self.value} @ pos:{self.position_id}"


class BlueprintPositionShelter(SharedMemoryModel):
    """Template shelter cloned into PositionShelter by instantiate_blueprint.

    Static template data — no decay fields. The clone produces a PositionShelter
    with ``change_per_day=0`` and ``source=""``.
    """

    blueprint_position = models.ForeignKey(
        BlueprintPosition, on_delete=models.CASCADE, related_name="shelters"
    )
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        related_name="blueprint_position_shelters",
    )
    value = models.IntegerField()

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(
                fields=["blueprint_position", "damage_type"],
                name="unique_bp_position_shelter",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"BlueprintShelter {self.damage_type_id}={self.value}"
            f" @ bp_pos:{self.blueprint_position_id}"
        )
