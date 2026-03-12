"""Service functions for querying IC time from the game clock."""

from datetime import datetime, timedelta

from world.game_clock.constants import (
    MONTH_TO_SEASON,
    PHASE_BOUNDARIES,
    Season,
    TimePhase,
)
from world.game_clock.models import GameClock


def get_ic_now(*, real_now: datetime | None = None) -> datetime | None:
    """Return the current IC datetime, or None if no clock exists."""
    clock = GameClock.get_active()
    if clock is None:
        return None
    return clock.get_ic_now(real_now=real_now)


def get_ic_season(*, real_now: datetime | None = None) -> Season | None:
    """Return the current IC season, or None if no clock exists."""
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    return MONTH_TO_SEASON[ic_now.month]


def get_ic_phase(*, real_now: datetime | None = None) -> TimePhase | None:
    """Return the current time-of-day phase, or None if no clock exists."""
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    season = MONTH_TO_SEASON[ic_now.month]
    dawn_start, day_start, dusk_start, night_start = PHASE_BOUNDARIES[season]
    hour = ic_now.hour + ic_now.minute / 60.0
    if hour < dawn_start:
        return TimePhase.NIGHT
    if hour < day_start:
        return TimePhase.DAWN
    if hour < dusk_start:
        return TimePhase.DAY
    if hour < night_start:
        return TimePhase.DUSK
    return TimePhase.NIGHT


def get_light_level(*, real_now: datetime | None = None) -> float | None:
    """Return a smooth 0.0-1.0 light level, or None if no clock exists."""
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    season = MONTH_TO_SEASON[ic_now.month]
    dawn_start, day_start, dusk_start, night_start = PHASE_BOUNDARIES[season]
    hour = ic_now.hour + ic_now.minute / 60.0

    min_light = 0.05
    max_light = 0.95

    if hour < dawn_start:
        return min_light
    if hour < day_start:
        # Dawn: linear interpolation from min_light to max_light
        progress = (hour - dawn_start) / (day_start - dawn_start)
        return min_light + progress * (max_light - min_light)
    if hour < dusk_start:
        return max_light
    if hour < night_start:
        # Dusk: linear interpolation from max_light to min_light
        progress = (hour - dusk_start) / (night_start - dusk_start)
        return max_light - progress * (max_light - min_light)
    return min_light


def get_ic_date_for_real_time(real_dt: datetime) -> datetime | None:
    """Convert a real datetime to IC datetime, or None if no clock exists."""
    clock = GameClock.get_active()
    if clock is None:
        return None
    return clock.get_ic_now(real_now=real_dt)


def get_real_time_for_ic_date(ic_dt: datetime) -> datetime | None:
    """Convert an IC datetime to real datetime, or None if no clock or paused/zero ratio."""
    clock = GameClock.get_active()
    if clock is None:
        return None
    if clock.paused or clock.time_ratio == 0:
        return None
    ic_elapsed = ic_dt - clock.anchor_ic_time
    real_elapsed = timedelta(seconds=ic_elapsed.total_seconds() / clock.time_ratio)
    return clock.anchor_real_time + real_elapsed
