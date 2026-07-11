"""RoomFeature strategy handlers for Field and Granary kinds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.room_features.services import _install_or_level_feature

if TYPE_CHECKING:
    from world.checks.types import CheckOutcome
    from world.projects.models import Project


def handle_field_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """FIELD strategy: install or level the feature instance + create FieldDetails.

    On first install (level 1), creates the ``RoomFeatureInstance`` and a
    ``FieldDetails`` row with the first available ``CropType``. On
    upgrade, just bumps the level (FieldDetails already exists).
    """
    from world.agriculture.models import CropType, FieldDetails  # noqa: PLC0415

    details = _install_or_level_feature(project, target_level)

    instance = details.target_room_profile.feature_instance
    if not hasattr(instance, "field_details"):
        crop = CropType.objects.first()
        if crop is None:
            return  # No crop types seeded yet — skip details creation.
        FieldDetails.objects.create(
            feature_instance=instance,
            crop_type=crop,
        )


def handle_granary_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """GRANARY strategy: install or level the feature instance + create GranaryDetails.

    On first install (level 1), creates the ``RoomFeatureInstance`` and a
    ``GranaryDetails`` row. On upgrade, just bumps the level.
    """
    from world.agriculture.models import GranaryDetails  # noqa: PLC0415

    details = _install_or_level_feature(project, target_level)

    instance = details.target_room_profile.feature_instance
    if not hasattr(instance, "granary_details"):
        GranaryDetails.objects.create(feature_instance=instance)
