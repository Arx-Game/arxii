"""Affinity-driven helpers for reactive flows.

Reusable across any reactive content that needs to read room aura state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def compute_intensity_difficulty(
    *,
    room: ObjectDB,
    affinity_name: str,
    base_difficulty: int,
    per_resonance_modifier: int,
) -> int:
    """Compute a check difficulty that scales with a room's affinity intensity.

    Returns ``base_difficulty + (count * per_resonance_modifier)`` where ``count``
    is the number of ``Resonance`` rows tagged on the room's ``RoomAuraProfile``
    whose ``Affinity`` matches the given name. If the room has no ``RoomAuraProfile``
    (i.e. is non-magical), ``count`` is 0 and ``base_difficulty`` is returned.

    V1-verified traversal: ObjectDB → RoomProfile → RoomAuraProfile. Both are
    OneToOne reverses; RoomAuraProfile is optional. Use the clean Django
    relations — NEVER touch Evennia's `.db` attribute handler.

    Args:
        room: The room ObjectDB.
        affinity_name: Name of the Affinity to count tagged resonances of.
        base_difficulty: Baseline difficulty when count is 0.
        per_resonance_modifier: Difficulty added per matched resonance.

    Returns:
        Computed difficulty value (int).
    """
    try:
        aura_profile = room.room_profile.room_aura_profile
    except ObjectDoesNotExist:
        return base_difficulty
    count = aura_profile.room_resonances.filter(
        resonance__affinity__name=affinity_name,
    ).count()
    return base_difficulty + (count * per_resonance_modifier)
