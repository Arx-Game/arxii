"""Result types for the weather system (#1522)."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from datetime import datetime

    from world.game_clock.constants import Season, TimePhase
    from world.weather.models import WeatherType


class ConditionsSummary(NamedTuple):
    """A point-in-time readout of IC time + the weather at a location (#1522).

    Any field may be ``None`` — no game clock yet (time fields), or no weather designated
    for the location (weather fields). The ``time`` command and the frontend render whatever
    is present.
    """

    ic_time: datetime | None
    phase: TimePhase | None
    season: Season | None
    weather_type: WeatherType | None
    emit_text: str | None
