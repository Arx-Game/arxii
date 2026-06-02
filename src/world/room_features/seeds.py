"""Idempotent seed helpers for the room_features system.

Per repo discipline (#683): seeds live in code, called via
``get_or_create``. NOT a committed fixture.

Plan 4 seeds:
- ``ensure_sanctum_kind`` — the one ``RoomFeatureKind`` row Plan 4 ships,
  plus its allowed owner-type rows (Persona OR Covenant organization).
  Other kinds (Library, Training Room, Lab, …) land via #675 content
  authoring.
"""

from __future__ import annotations

from world.room_features.constants import (
    RoomFeatureOwnerType,
    RoomFeatureServiceStrategy,
)
from world.room_features.models import RoomFeatureKind, RoomFeatureKindOwnerType

SANCTUM_KIND_NAME = "Sanctum"
SANCTUM_MAX_LEVEL = 5


def ensure_sanctum_kind() -> RoomFeatureKind:
    """Get-or-create the Sanctum ``RoomFeatureKind`` row + owner-type rules.

    Idempotent. Two ``RoomFeatureKindOwnerType`` rows are seeded —
    ``PERSONA`` and ``ORG_COVENANT`` — enforcing the spec's
    ``required_building_owner_types`` constraint for Sanctum.
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.SANCTUM,
        defaults={
            "name": SANCTUM_KIND_NAME,
            "description": (
                "A consecrated room — Personal home or Covenant sacred "
                "ground — that generates passive resonance income for "
                "woven threads via the Ritual of Homecoming."
            ),
            "max_level": SANCTUM_MAX_LEVEL,
        },
    )
    for owner_type in (
        RoomFeatureOwnerType.PERSONA,
        RoomFeatureOwnerType.ORGANIZATION_COVENANT,
    ):
        RoomFeatureKindOwnerType.objects.get_or_create(
            feature_kind=kind,
            owner_type=owner_type,
        )
    return kind


def ensure_plan_4_seeds() -> None:
    """Convenience: seed everything Plan 4 needs at the framework layer.

    Safe to call multiple times (each component is idempotent). Sanctum-
    specific seeds (``Ritual`` rows for Homecoming + Purging) live in
    ``world.magic`` and are seeded by its own seed module.
    """
    ensure_sanctum_kind()
