"""Idempotent seed helpers for evennia_extensions lookup tables.

Per repo discipline (#683): seeds live in code, called via ``get_or_create``.
NOT a committed fixture.
"""

from __future__ import annotations

from evennia_extensions.models import RoomSizeTier

# PLACEHOLDER magnitudes (#670) — ratified ladder shape; absolute values await the
# economy/tuning pass. Admin-editable rows; code must never hardcode unit values.
ROOM_SIZE_TIERS: tuple[tuple[str, int], ...] = (
    ("Micro", 2),
    ("Cramped", 5),
    ("Snug", 10),
    ("Modest", 25),
    ("Spacious", 50),
    ("Grand", 100),
    ("Vast", 250),
    ("Sprawling", 500),
    ("Expanse", 2500),
)

DEFAULT_ROOM_SIZE_NAME = "Modest"


def ensure_room_size_tiers() -> None:
    """Get-or-create the room-size unit ladder."""
    for name, units in ROOM_SIZE_TIERS:
        RoomSizeTier.objects.get_or_create(name=name, defaults={"units": units})
