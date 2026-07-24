from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.descriptors import ReverseOneToOneOrNone
from world.areas.positioning.constants import PositionKind, RampartCrackState, RampartSignature

_DAMAGE_TYPE_MODEL = "conditions.DamageType"

# Instance-dict names of the Prefetch/query shared-interface caches on Position.
_POSITION_EDGE_CACHES = ("passable_edges_as_a", "passable_edges_as_b", "all_edges_as_a")


def _pop_room_graph(room) -> None:
    """Drop *room*'s cached ``positions_cached`` entry (targeted, never a blanket
    cached-property clear — the identity-mapped Room also caches live state such
    as ``scene_data``/``trigger_handler`` whose identity must survive mutations)."""
    if room is not None:
        room.__dict__.pop("positions_cached", None)


def invalidate_position_graph_caches(room) -> None:
    """Invalidate the full cached positions graph for *room*.

    Pops the room's ``positions_cached`` plus every in-room Position's edge
    caches (Positions are SharedMemoryModel singletons, so their cached edge
    lists outlive requests too). Model ``save()``/``delete()`` call cheaper
    targeted pops themselves; bulk mutation paths (``QuerySet.delete()``,
    ``bulk_create``) bypass those hooks and MUST call this explicitly.
    """
    if room is None:
        return
    _pop_room_graph(room)
    for position in Position.objects.filter(room=room):
        for name in _POSITION_EDGE_CACHES:
            position.__dict__.pop(name, None)


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
    """A named tactical region within a room. The node of the positioning graph.

    Saving/deleting a Position invalidates the room's cached ``positions_cached``
    (identity-mapped rooms would otherwise serve a stale graph across requests);
    the invalidation is targeted — only the graph cache, never the room's other
    cached properties (scene_data et al. hold live state).
    """

    room = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE, related_name="positions")
    elevation_anchor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elevated_over",
        help_text="The position immediately below this one (null = solid floor / bottom).",
    )
    layout_x = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Cosmetic tactical-map column (#2006) — never gates creation or "
            "movement. NULL (with layout_y) = auto-laid-out on the map."
        ),
    )
    layout_y = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text="Cosmetic tactical-map row (#2006). See layout_x.",
    )

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(fields=["room", "name"], name="unique_position_per_room"),
        ]
        ordering = ["room", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()}) in {self.room_id}"

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        _pop_room_graph(self.room)

    def delete(self, *args, **kwargs):
        room = self.room
        result = super().delete(*args, **kwargs)
        _pop_room_graph(room)
        return result

    # Prefetch/query shared interfaces (see ObjectParent.positions_cached):
    # combat's encounter queryset pre-fills these names via nested
    # Prefetch(to_attr=...); independent callers get the same shape lazily.

    @cached_property
    def passable_edges_as_a(self) -> list["PositionEdge"]:
        return list(self.edges_as_a.filter(is_passable=True).only("position_a_id", "position_b_id"))

    @cached_property
    def passable_edges_as_b(self) -> list["PositionEdge"]:
        return list(self.edges_as_b.filter(is_passable=True).only("position_a_id", "position_b_id"))

    @cached_property
    def all_edges_as_a(self) -> list["PositionEdge"]:
        return list(self.edges_as_a.select_related("gating_challenge__template"))

    rampart_or_none = ReverseOneToOneOrNone("rampart")


class PositionEdge(PositionEdgeBase):
    """Traversable adjacency between two positions in the same room.

    Stored canonically (position_a_id < position_b_id). A non-null
    gating_challenge means crossing is gated by that Challenge (the
    cross-the-chasm gate); its approaches carry capability routes.

    Saving/deleting an edge invalidates both endpoints' cached edge lists and
    the room's ``positions_cached`` graph — targeted pops only, never a blanket
    cached-property clear.
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
    duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="For conjured obstacles: rounds until expiry. Null = permanent (staff-authored).",
    )
    created_by_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conjured_obstacles",
        help_text=(
            "Provenance: the caster who conjured this obstacle. Null for staff-authored edges."
        ),
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

    def _invalidate_graph_caches(self) -> None:
        for position in (self.position_a, self.position_b):
            if position is None:
                continue
            for name in _POSITION_EDGE_CACHES:
                position.__dict__.pop(name, None)
        if self.position_a is not None:
            _pop_room_graph(self.position_a.room)

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        self._invalidate_graph_caches()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        self._invalidate_graph_caches()
        return result


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
    layout_x = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Cosmetic tactical-map column (#2006), copied to the cloned "
            "Position by instantiate_blueprint. NULL = auto-laid-out."
        ),
    )
    layout_y = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text="Cosmetic tactical-map row (#2006). See layout_x.",
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

    # ObjectDB by design (#2608): props and hazards (volatile objects, detonation
    # targets) occupy positions exactly like characters — mirrors db_location.
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
        _DAMAGE_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="position_shelters",
    )
    value = models.IntegerField(
        help_text="Magnitude of shelter. Added to the room's cascade value."
    )
    applies_to_attacks = models.BooleanField(
        default=False,
        help_text=(
            "When True, this shelter applies to incoming attacks of this "
            "damage type (attack-cover). When False (default), it applies "
            "to environmental hazards only."
        ),
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
        _DAMAGE_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="blueprint_position_shelters",
    )
    value = models.IntegerField()
    applies_to_attacks = models.BooleanField(
        default=False,
        help_text=(
            "When True, this shelter applies to incoming attacks of this "
            "damage type (attack-cover). When False (default), it applies "
            "to environmental hazards only."
        ),
    )

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


class RampartElementProfile(SharedMemoryModel):
    """A reusable element (Stone/Wind/Fire/Thorn/...) a Rampart is raised from (#2209).

    Authored content: one row per element, shared across every Rampart cast from
    it. ``signature_behavior`` selects which of the four authored behaviors
    (see ``RampartSignature``) this element grants; ``signature_value`` and the
    optional damage-type/condition FKs parameterize that behavior (e.g. Fire's
    retaliation damage, Wind's missile-ward adjustment, Thorn's grasping
    condition). Per-damage-type resist/vulnerability lives on the related
    ``RampartElementResistance`` rows.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    signature_behavior = models.CharField(
        max_length=20,
        choices=RampartSignature.choices,
        help_text="The one authored behavior this element grants its Ramparts.",
    )
    signature_value = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Magnitude for signature_behavior: missile/area resist adjustment "
            "(MISSILE_WARD) or retaliation damage (MELEE_RETALIATION)."
        ),
    )
    signature_damage_type = models.ForeignKey(
        _DAMAGE_TYPE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rampart_signature_profiles",
        help_text="Retaliation damage type (MELEE_RETALIATION). Unused by other behaviors.",
    )
    signature_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rampart_signature_profiles",
        help_text="Condition applied to a grasped opponent (GRASPING). Unused by other behaviors.",
    )

    class Meta:
        app_label = "areas"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RampartElementResistance(SharedMemoryModel):
    """A per-damage-type resist/vulnerability row for a RampartElementProfile (#2209).

    ``value`` is signed: positive resists (shrinks incoming chip damage),
    negative is a vulnerability (grows it). Absent damage types resist 0.
    """

    profile = models.ForeignKey(
        RampartElementProfile, on_delete=models.CASCADE, related_name="resistances"
    )
    damage_type = models.ForeignKey(
        _DAMAGE_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="rampart_resistances",
    )
    value = models.SmallIntegerField(
        help_text="Signed: positive resists, negative is a vulnerability."
    )

    class Meta:
        app_label = "areas"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "damage_type"], name="unique_rampart_resistance_per_type"
            ),
        ]
        ordering = ["profile", "damage_type"]

    def __str__(self) -> str:
        return f"{self.profile_id}:{self.damage_type_id}={self.value}"


class Rampart(SharedMemoryModel):
    """A living barrier raised on a Position — a conjured, damageable wall (#2209).

    One rampart per position (unique FK). Re-casting on an occupied position
    replaces the existing row (see ``raise_rampart``). ``integrity`` chips down
    as strikes are intercepted (``damage_rampart``); it collapses (row deleted)
    at 0.
    """

    position = models.OneToOneField(Position, on_delete=models.CASCADE, related_name="rampart")
    element_profile = models.ForeignKey(RampartElementProfile, on_delete=models.PROTECT)
    integrity = models.PositiveSmallIntegerField()
    max_integrity = models.PositiveSmallIntegerField()
    created_by_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ramparts",
        help_text="Provenance: the caster who raised this rampart. Null for staff-authored.",
    )
    duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Rounds until expiry. Null = until collapse or scene end.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "areas"
        ordering = ["position"]

    @property
    def crack_state(self) -> str:
        """Coarse integrity band: INTACT > 2/3 max, CRACKED > 1/3, else CRUMBLING."""
        if self.integrity * 3 > self.max_integrity * 2:
            return RampartCrackState.INTACT
        if self.integrity * 3 > self.max_integrity:
            return RampartCrackState.CRACKED
        return RampartCrackState.CRUMBLING

    def __str__(self) -> str:
        return (
            f"Rampart({self.element_profile_id}) "
            f"{self.integrity}/{self.max_integrity} @ {self.position_id}"
        )
