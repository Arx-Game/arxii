"""Brig room-feature service handler (#1862).

Mirrors ``world.room_features.vault_services.handle_vault_progression``:
installs or levels a Brig ``RoomFeatureInstance`` and maintains its
``BrigDetails`` payload (max_prisoners scaled by level).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.room_features.constants import BRIG_CAPACITY_PER_LEVEL
from world.room_features.services import _install_or_level_feature

if TYPE_CHECKING:
    from world.checks.types import CheckOutcome
    from world.projects.models import Project


def handle_brig_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """BRIG strategy (#1862): install/level the feature + create BrigDetails.

    At L1: creates ``RoomFeatureInstance`` via ``_install_or_level_feature``,
    then creates ``BrigDetails`` with ``max_prisoners=target_level *
    BRIG_CAPACITY_PER_LEVEL``.
    At L2+: bumps instance level and updates ``max_prisoners``.
    """
    from world.room_features.models import BrigDetails  # noqa: PLC0415

    details = _install_or_level_feature(project, target_level)
    instance = details.target_room_profile.feature_instance
    brig, created = BrigDetails.objects.get_or_create(
        feature_instance=instance,
        defaults={
            "max_prisoners": target_level * BRIG_CAPACITY_PER_LEVEL,
        },
    )
    if not created:
        brig.max_prisoners = instance.level * BRIG_CAPACITY_PER_LEVEL
        brig.save(update_fields=["max_prisoners"])
