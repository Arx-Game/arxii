"""Room activity bands derived from the TRAFFIC location stat (#745).

TRAFFIC (0-100, the existing cascade stat) is anonymous public flow. We map it
to a qualitative **activity band** + a spread multiplier. Players see the band
word ("Bustling"); the multiplier feeds the legend-spread math under the hood.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.game_clock.constants import TimePhase

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

# IC time-of-day multiplier on a room's traffic before banding (#745 Phase 3).
# A place waxes busier toward evening and empties at night/dawn. Tunable.
PHASE_TRAFFIC_FACTOR: dict[TimePhase, float] = {
    TimePhase.DAWN: 0.6,
    TimePhase.DAY: 1.0,
    TimePhase.DUSK: 1.15,
    TimePhase.NIGHT: 0.5,
}

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


def room_activity_band(
    room: DefaultObject | None, *, ic_phase: TimePhase | None = None
) -> ActivityBand:
    """Activity band for an Evennia room object (e.g. ``scene.location``).

    Reads the room's cascade-resolved TRAFFIC stat, then bends it by the IC
    time-of-day (a market reads Busy by day, Bustling at dusk, Quiet at dawn).
    Rooms with no profile (or a None room) fall through to the TRAFFIC default.
    ``ic_phase`` defaults to the live IC phase; pass it to override (tests).
    """
    from world.game_clock.services import get_ic_phase  # noqa: PLC0415
    from world.locations.constants import StatKey  # noqa: PLC0415
    from world.locations.services import effective_stats_for_rooms  # noqa: PLC0415

    if room is None:
        traffic = 50
    else:
        stats = effective_stats_for_rooms([room], [StatKey.TRAFFIC])
        traffic = stats.get(room.pk, {}).get(StatKey.TRAFFIC, 50)

    phase = ic_phase if ic_phase is not None else get_ic_phase()
    factor = PHASE_TRAFFIC_FACTOR.get(phase, 1.0) if phase is not None else 1.0
    effective = max(0, min(100, round(traffic * factor)))
    return band_for_traffic(effective)
