"""Models for the Room Features framework.

Subsystem E of Plan 4. Provides the reusable install/upgrade machinery
that Sanctum (and future Library, Training Room, Lab, etc.) plug into.
Per-kind state lives in the feature's home-app details model (e.g.,
:class:`world.magic.models.sanctum.SanctumDetails`), keyed by OneToOne
back to :class:`RoomFeatureInstance`.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.room_features.constants import (
    RoomFeatureOwnerType,
    RoomFeatureServiceStrategy,
)


class RoomFeatureKind(SharedMemoryModel):
    """Catalog row for a kind of installable room feature.

    Open catalog — staff-authorable. Plan 4 ships exactly one row
    (Sanctum) via :func:`world.room_features.seeds.ensure_sanctum_kind`.
    Other kinds (Library, Training Room, Lab, …) land via #675 content
    authoring without touching this model.

    Each row pairs a ``service_strategy`` key (selecting the per-kind
    install/upgrade handler from
    :mod:`world.room_features.services`) with the catalog metadata the
    install UI needs to filter and present choices.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True,
        help_text="Admin-editable flavor describing what this feature is.",
    )
    max_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text=(
            "Cap on the feature's level. Per-kind: Sanctum=5, Library might be 10, "
            "Training Room might be 3. Bounds ``RoomFeatureInstance.level`` and "
            "the install/upgrade wizard's target-level picker."
        ),
    )
    service_strategy = models.CharField(
        max_length=32,
        choices=RoomFeatureServiceStrategy.choices,
        unique=True,
        help_text=(
            "Key into the service-strategy registry. Each row's strategy is "
            "registered by the kind's home app at app-ready time. "
            "Unique — one kind per strategy."
        ),
    )
    allowed_building_kinds = models.ManyToManyField(
        "buildings.BuildingKind",
        blank=True,
        related_name="installable_features",
        help_text=(
            "Restrict installation to buildings of these kinds. Empty m2m "
            "means any building kind is allowed."
        ),
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(max_level__gte=1),
                name="room_feature_kind_max_level_gte_1",
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RoomFeatureKindOwnerType(SharedMemoryModel):
    """Allowed owner-type rows for a ``RoomFeatureKind``.

    Sanctum requires ``PERSONA`` OR ``ORG_COVENANT`` — two rows.
    Future "Heraldic Hall" might require only ``ORG_NOBLE``. Empty set
    (zero rows) means the kind imposes no owner-type restriction; the
    seed-side discipline is to author at least one row per kind that
    actually restricts ownership.
    """

    feature_kind = models.ForeignKey(
        RoomFeatureKind,
        on_delete=models.CASCADE,
        related_name="required_building_owner_types",
    )
    owner_type = models.CharField(
        max_length=20,
        choices=RoomFeatureOwnerType.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feature_kind", "owner_type"],
                name="room_feature_kind_owner_type_unique",
            ),
        ]
        ordering = ["feature_kind", "owner_type"]

    def __str__(self) -> str:
        return f"{self.feature_kind.name} allows {self.get_owner_type_display()}"


class RoomFeatureInstance(SharedMemoryModel):
    """A feature installed in one specific room.

    OneToOne with ``RoomProfile`` enforces the **one-feature-per-room**
    rule at the schema level. Per-kind state (Sanctum's resonance_type
    etc.) lives in a details model keyed by OneToOne back to this row.
    """

    room_profile = models.OneToOneField(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="feature_instance",
        primary_key=True,
        help_text="The room this feature is installed in (one feature per room).",
    )
    feature_kind = models.ForeignKey(
        RoomFeatureKind,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Current level. Bounded by ``feature_kind.max_level`` at write time.",
    )
    installed_at = models.DateTimeField(default=timezone.now)
    last_upgraded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set on each successful upgrade past level 1; null at install.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(level__gte=1),
                name="room_feature_instance_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.feature_kind.name} L{self.level} @ room {self.room_profile_id}"


class RoomFeatureProgressionDetails(SharedMemoryModel):
    """Per-(ROOM_FEATURE_PROGRESSION Project) details payload.

    Created when an install/upgrade Project spawns; consumed by
    :func:`world.room_features.services.complete_room_feature_progression`
    when the project resolves. Mirrors Plan 3's
    ``BuildingConstructionDetails`` shape.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="room_feature_progression_details",
        primary_key=True,
    )
    target_room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.PROTECT,
        related_name="feature_progression_projects",
        help_text="The room the feature will be installed in or upgraded.",
    )
    target_feature_kind = models.ForeignKey(
        RoomFeatureKind,
        on_delete=models.PROTECT,
        related_name="progression_projects",
    )
    target_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text=(
            "The level this project aims to reach. Install → 1; upgrade → "
            "current+1 (or higher). Bounded by ``feature_kind.max_level`` at "
            "project-creation time."
        ),
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(target_level__gte=1),
                name="room_feature_progression_target_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Progression#{self.project_id}: {self.target_feature_kind.name} L{self.target_level}"
        )
