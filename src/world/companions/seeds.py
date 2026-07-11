"""Seed content for the Companions app (#1863)."""

from __future__ import annotations


def ensure_stables_kind() -> None:
    """Idempotently create the Stables RoomFeatureKind (#1863).

    The Stables is a physical room feature (PROJECT install mechanism) that
    provides a Companion Capacity bonus to characters with standing in the
    room. Max level 5 (placeholder — staff-tunable in admin).
    """
    from world.room_features.constants import (  # noqa: PLC0415
        RoomFeatureInstallMechanism,
        RoomFeatureServiceStrategy,
    )
    from world.room_features.models import RoomFeatureKind  # noqa: PLC0415

    RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.STABLES,
        defaults={
            "name": "Stables",
            "description": (
                "Housing for mounts and beasts. Increases the owner's Companion Capacity."
            ),
            "max_level": 5,
            "install_mechanism": RoomFeatureInstallMechanism.PROJECT,
        },
    )
