"""Brig room-feature service handler (#1862).

Mirrors ``world.room_features.vault_services.handle_vault_progression``:
installs or levels a Brig ``RoomFeatureInstance`` and maintains its
``BrigDetails`` payload (max_prisoners scaled by level).

``find_brig_for_area``/``brig_has_capacity`` were promoted here from
``world.mechanics.effect_handlers`` (#2378 Task 4) so both the CAPTURE
consequence-effect path and the justice pipeline's arrest custody can share
one Brig lookup instead of two copies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.room_features.constants import BRIG_CAPACITY_PER_LEVEL
from world.room_features.services import _install_or_level_feature

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
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


def find_brig_for_area(area: Area | None) -> RoomProfile | None:
    """Find an active Brig room feature anywhere in ``area`` (#1862, promoted #2378).

    Promoted verbatim (minus the building resolution, which callers now do
    themselves — or skip, when they already hold the Area) from
    ``mechanics.effect_handlers._find_brig_for_captor``. Returns the Brig's
    ``RoomProfile`` if found, ``None`` otherwise (#2608 — ``Captivity.holding_room``
    takes the profile, so no ObjectDB round-trip).
    """
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    if area is None or area.pk is None:
        return None
    brig_instance = (
        RoomFeatureInstance.objects.filter(
            feature_kind__service_strategy=RoomFeatureServiceStrategy.BRIG,
            room_profile__area_id=area.pk,
            dissolved_at__isnull=True,
        )
        .select_related("room_profile", "brig_details")
        .first()
    )
    if brig_instance is None:
        return None
    return brig_instance.room_profile


def brig_has_capacity(brig_room: RoomProfile) -> bool:
    """Check if the Brig room has capacity for another prisoner (#1862)."""
    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.captivity.models import Captivity  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    instance = (
        RoomFeatureInstance.objects.filter(
            room_profile=brig_room,
            dissolved_at__isnull=True,
        )
        .select_related("brig_details")
        .first()
    )
    if instance is None or not hasattr(instance, "brig_details"):
        return False
    max_prisoners = instance.brig_details.max_prisoners
    current = Captivity.objects.filter(
        holding_room=brig_room,
        status=CaptivityStatus.HELD,
    ).count()
    return current < max_prisoners
