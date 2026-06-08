"""Room activity bands derived from the TRAFFIC location stat (#745).

TRAFFIC (0-100, the existing cascade stat) is anonymous public flow. We map it
to a qualitative **activity band** + a spread multiplier. Players see the band
word ("Bustling"); the multiplier feeds the legend-spread math under the hood.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

# (TRAFFIC threshold, band label, spread multiplier), ascending by threshold.
# The highest threshold <= the value wins. Tunable.
ACTIVITY_BANDS: list[tuple[int, str, float]] = [
    (0, "Empty", 0.0),
    (1, "Nearly deserted", 0.1),
    (6, "Sparse", 0.3),
    (15, "Quiet", 0.5),
    (30, "Steady", 0.75),
    (50, "Busy", 1.0),
    (70, "Bustling", 1.4),
    (85, "Packed", 1.8),
    (100, "Thronging", 2.2),
]


@dataclass(frozen=True)
class ActivityBand:
    """A room's current activity: the player-facing label + spread multiplier."""

    label: str
    multiplier: float


def band_for_traffic(traffic: int) -> ActivityBand:
    """Map a 0-100 TRAFFIC value to its activity band + spread multiplier."""
    chosen = ACTIVITY_BANDS[0]
    for threshold, label, multiplier in ACTIVITY_BANDS:
        if traffic >= threshold:
            chosen = (threshold, label, multiplier)
    return ActivityBand(label=chosen[1], multiplier=chosen[2])


def room_activity_band(room: DefaultObject | None) -> ActivityBand:
    """Activity band for an Evennia room object (e.g. ``scene.location``).

    Reads the room's cascade-resolved TRAFFIC stat. Rooms with no profile (or a
    None room) fall through to the TRAFFIC default (Busy baseline).
    """
    from world.locations.constants import StatKey  # noqa: PLC0415
    from world.locations.services import effective_stats_for_rooms  # noqa: PLC0415

    if room is None:
        return band_for_traffic(50)
    stats = effective_stats_for_rooms([room], [StatKey.TRAFFIC])
    traffic = stats.get(room.pk, {}).get(StatKey.TRAFFIC, 50)
    return band_for_traffic(traffic)
