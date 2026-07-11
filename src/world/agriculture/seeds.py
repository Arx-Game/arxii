"""Idempotent seed helpers for the agriculture system.

Per repo discipline (#683): seeds live in code, called via ``get_or_create``.
"""

from __future__ import annotations

from world.agriculture.constants import FIELD_MAX_LEVEL, GRANARY_MAX_LEVEL
from world.agriculture.models import CropType
from world.room_features.constants import (
    RoomFeatureInstallMechanism,
    RoomFeatureServiceStrategy,
)
from world.room_features.models import RoomFeatureKind

FIELD_KIND_NAME = "Field"
GRANARY_KIND_NAME = "Granary"


def ensure_field_kind() -> RoomFeatureKind:
    """Get-or-create the Field ``RoomFeatureKind`` row.

    A Field produces food on a daily cron tick into an uncollected pool.
    Installs via PROJECT (physical, collaborative). No owner-type
    restriction (any building owner may install).
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.FIELD,
        defaults={
            "name": FIELD_KIND_NAME,
            "max_level": FIELD_MAX_LEVEL,
            "install_mechanism": RoomFeatureInstallMechanism.PROJECT,
            "description": (
                "PLACEHOLDER — Field kind: produces food on a daily cron tick "
                "into an uncollected pool. Collect actively to move food to "
                "the domain's stockpile."
            ),
        },
    )
    return kind


def ensure_granary_kind() -> RoomFeatureKind:
    """Get-or-create the Granary ``RoomFeatureKind`` row.

    A Granary gates the domain's max food storage capacity (level ×
    ``granary_capacity_per_level``). Installs via PROJECT.
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.GRANARY,
        defaults={
            "name": GRANARY_KIND_NAME,
            "max_level": GRANARY_MAX_LEVEL,
            "install_mechanism": RoomFeatureInstallMechanism.PROJECT,
            "description": (
                "PLACEHOLDER — Granary kind: gates the domain's max food "
                "storage capacity. Higher levels = more storage."
            ),
        },
    )
    return kind


def ensure_field_granary_kinds() -> RoomFeatureKind:
    """Seed both Field and Granary kinds. Returns the Field kind."""
    field = ensure_field_kind()
    ensure_granary_kind()
    return field


def ensure_starter_crop_types() -> None:
    """Seed a few starter CropType rows with PLACEHOLDER production values."""
    starters = [
        ("Wheat", 10, "A staple grain."),
        ("Barley", 8, "A hardy grain for brewing and bread."),
        ("Root Vegetables", 6, "Nutritious tubers that grow in poor soil."),
    ]
    for name, production, description in starters:
        CropType.objects.get_or_create(
            name=name,
            defaults={"base_production": production, "description": description},
        )
