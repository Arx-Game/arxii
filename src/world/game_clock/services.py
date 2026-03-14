"""Service functions for querying IC time from the game clock."""

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.game_clock.constants import (
    MONTH_TO_SEASON,
    PHASE_BOUNDARIES,
    Season,
    TimePhase,
)
from world.game_clock.models import GameClock, GameClockHistory
from world.game_clock.types import ClockError


def get_ic_now(*, real_now: datetime | None = None) -> datetime | None:
    """Return the current IC datetime, or None if no clock exists."""
    clock = GameClock.get_active()
    if clock is None:
        return None
    return clock.get_ic_now(real_now=real_now)


def season_from_ic_time(ic_now: datetime) -> Season:
    """Derive the IC season from a concrete IC datetime."""
    return MONTH_TO_SEASON[ic_now.month]


def phase_from_ic_time(ic_now: datetime) -> TimePhase:
    """Derive the time-of-day phase from a concrete IC datetime."""
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


def light_level_from_ic_time(ic_now: datetime) -> float:
    """Derive a smooth 0.0-1.0 light level from a concrete IC datetime."""
    season = MONTH_TO_SEASON[ic_now.month]
    dawn_start, day_start, dusk_start, night_start = PHASE_BOUNDARIES[season]
    hour = ic_now.hour + ic_now.minute / 60.0

    min_light = 0.05
    max_light = 0.95

    if hour < dawn_start:
        return min_light
    if hour < day_start:
        progress = (hour - dawn_start) / (day_start - dawn_start)
        return min_light + progress * (max_light - min_light)
    if hour < dusk_start:
        return max_light
    if hour < night_start:
        progress = (hour - dusk_start) / (night_start - dusk_start)
        return max_light - progress * (max_light - min_light)
    return min_light


def get_ic_season(*, real_now: datetime | None = None) -> Season | None:
    """Return the current IC season, or None if no clock exists."""
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    return season_from_ic_time(ic_now)


def get_ic_phase(*, real_now: datetime | None = None) -> TimePhase | None:
    """Return the current time-of-day phase, or None if no clock exists."""
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    return phase_from_ic_time(ic_now)


def get_light_level(*, real_now: datetime | None = None) -> float | None:
    """Return a smooth 0.0-1.0 light level, or None if no clock exists."""
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    return light_level_from_ic_time(ic_now)


def get_ic_date_for_real_time(real_dt: datetime) -> datetime | None:
    """Convert a real datetime to IC datetime, or None if no clock exists."""
    clock = GameClock.get_active()
    if clock is None:
        return None
    return clock.get_ic_now(real_now=real_dt)


def get_real_time_for_ic_date(ic_dt: datetime) -> datetime | None:
    """Convert an IC datetime to real datetime, or None if no clock exists.

    Raises:
        ClockError: If the clock is paused or has a zero time ratio (conversion
            is mathematically undefined in those states).
    """
    clock = GameClock.get_active()
    if clock is None:
        return None
    if clock.paused or clock.time_ratio == 0:
        raise ClockError(ClockError.CONVERSION_UNAVAILABLE)
    ic_elapsed = ic_dt - clock.anchor_ic_time
    real_elapsed = timedelta(seconds=ic_elapsed.total_seconds() / clock.time_ratio)
    return clock.anchor_real_time + real_elapsed


# ---------------------------------------------------------------------------
# Clock management services
# ---------------------------------------------------------------------------


def _log_clock_change(
    *,
    clock: GameClock,
    old_state: tuple[datetime, datetime, float],
    changed_by: AccountDB,
    reason: str,
) -> GameClockHistory:
    """Create a GameClockHistory entry recording a clock change.

    Args:
        clock: The clock after the change (new state read from its fields).
        old_state: Tuple of (anchor_real_time, anchor_ic_time, time_ratio)
            captured before the change.
        changed_by: The account that initiated the change.
        reason: Human-readable reason for the change.
    """
    old_real, old_ic, old_ratio = old_state
    return GameClockHistory.objects.create(
        changed_by=changed_by,
        old_anchor_real_time=old_real,
        old_anchor_ic_time=old_ic,
        old_time_ratio=old_ratio,
        new_anchor_real_time=clock.anchor_real_time,
        new_anchor_ic_time=clock.anchor_ic_time,
        new_time_ratio=clock.time_ratio,
        reason=reason,
    )


@transaction.atomic()
def set_clock(
    *,
    new_ic_time: datetime,
    changed_by: AccountDB,
    reason: str = "",
) -> GameClock:
    """Set the game clock IC time, creating it if it doesn't exist.

    On initial creation no history entry is logged. On subsequent calls
    the clock is re-anchored to now and a history entry is recorded.
    """
    now = timezone.now()
    clock = GameClock.get_active()

    if clock is None:
        clock = GameClock(
            anchor_real_time=now,
            anchor_ic_time=new_ic_time,
        )
        clock.save()
        return clock

    # Existing clock — capture old state, re-anchor, log history
    old_state = (clock.anchor_real_time, clock.anchor_ic_time, clock.time_ratio)

    clock.anchor_real_time = now
    clock.anchor_ic_time = new_ic_time
    clock.save(update_fields=["anchor_real_time", "anchor_ic_time"])

    _log_clock_change(
        clock=clock,
        old_state=old_state,
        changed_by=changed_by,
        reason=reason,
    )
    return clock


@transaction.atomic()
def set_time_ratio(
    *,
    ratio: float,
    changed_by: AccountDB,
    reason: str = "",
) -> GameClock:
    """Change the time ratio, re-anchoring IC time to preserve continuity."""
    if ratio <= 0:
        raise ClockError(ClockError.INVALID_RATIO)

    clock = GameClock.get_active()
    if clock is None:
        raise ClockError(ClockError.NOT_CONFIGURED)

    old_state = (clock.anchor_real_time, clock.anchor_ic_time, clock.time_ratio)

    now = timezone.now()
    current_ic = clock.get_ic_now(real_now=now)

    clock.anchor_real_time = now
    clock.anchor_ic_time = current_ic
    clock.time_ratio = ratio
    clock.save(update_fields=["anchor_real_time", "anchor_ic_time", "time_ratio"])

    _log_clock_change(
        clock=clock,
        old_state=old_state,
        changed_by=changed_by,
        reason=reason,
    )
    return clock


@transaction.atomic()
def pause_clock(
    *,
    changed_by: AccountDB,
    reason: str = "",
) -> GameClock:
    """Pause the game clock, freezing IC time at its current value."""
    clock = GameClock.get_active()
    if clock is None:
        raise ClockError(ClockError.NOT_CONFIGURED)
    if clock.paused:
        raise ClockError(ClockError.ALREADY_PAUSED)

    old_state = (clock.anchor_real_time, clock.anchor_ic_time, clock.time_ratio)

    now = timezone.now()
    current_ic = clock.get_ic_now(real_now=now)

    clock.anchor_real_time = now
    clock.anchor_ic_time = current_ic
    clock.paused = True
    clock.save(update_fields=["anchor_real_time", "anchor_ic_time", "paused"])

    _log_clock_change(
        clock=clock,
        old_state=old_state,
        changed_by=changed_by,
        reason=reason,
    )
    return clock


@transaction.atomic()
def unpause_clock(
    *,
    changed_by: AccountDB,
    reason: str = "",
) -> GameClock:
    """Unpause the game clock, resuming IC time from where it was paused."""
    clock = GameClock.get_active()
    if clock is None:
        raise ClockError(ClockError.NOT_CONFIGURED)
    if not clock.paused:
        raise ClockError(ClockError.NOT_PAUSED)

    old_state = (clock.anchor_real_time, clock.anchor_ic_time, clock.time_ratio)

    now = timezone.now()
    # IC time stays at anchor (where we paused), only real anchor moves to now
    clock.anchor_real_time = now
    clock.paused = False
    clock.save(update_fields=["anchor_real_time", "paused"])

    _log_clock_change(
        clock=clock,
        old_state=old_state,
        changed_by=changed_by,
        reason=reason,
    )
    return clock
