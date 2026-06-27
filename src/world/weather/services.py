"""Read services for the weather system (#1522).

Three concerns:

- **Climate resolution** — ``get_effective_climate`` walks the area hierarchy
  most-specific-wins (mirrors ``world.areas.services.get_effective_realm``).
- **Seasonal temperature shift** — ``current_temperature_shift`` reads the IC clock's
  month and looks up the global per-month curve.
- **Exposure decomposition** — ``climate_exposure_base`` turns a resolved climate's
  signed temperature/moisture (plus the seasonal shift) into the per-axis floored base
  that ``world.locations.services.felt_exposure`` folds into the comfort cascade.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from world.game_clock.services import get_ic_now, get_ic_phase, get_ic_season
from world.locations.constants import KeyType, LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.weather.constants import (
    MONTH_TEMPERATURE_SHIFT,
    WEATHER_FADE_DAYS,
    WEATHER_SOURCE_PREFIX,
)
from world.weather.models import RegionWeatherState, WeatherType

if TYPE_CHECKING:
    from datetime import datetime

    from world.areas.models import Area
    from world.game_clock.constants import Season, TimePhase
    from world.weather.models import Climate, WeatherEmit


def _weighted_choice(items: list, weights: list[int]):
    """Pick one item by weight using the CSPRNG (avoids ruff's S311 on ``random``).

    ``secrets`` has no weighted helper, so walk the cumulative weights with one random int.
    """
    total = sum(weights)
    if total <= 0:
        return items[0]
    target = secrets.randbelow(total)
    cumulative = 0
    for item, weight in zip(items, weights, strict=True):
        cumulative += weight
        if target < cumulative:
            return item
    return items[-1]


def get_effective_climate(area: Area | None) -> Climate | None:
    """Walk up the area hierarchy to the nearest climate assignment (#1522).

    Most-specific-wins: a sub-region's own climate shadows its parent's. Returns None if
    no ancestor (or the area itself) designates a climate. Mirrors ``get_effective_realm``.
    """
    node = area
    while node is not None:
        if node.climate_id is not None:
            return node.climate
        node = node.parent
    return None


def month_temperature_shift(month: int) -> int:
    """The global temperature shift for an IC month (1–12); 0 if out of range."""
    return MONTH_TEMPERATURE_SHIFT.get(month, 0)


def current_temperature_shift(*, real_now: datetime | None = None) -> int:
    """The current global seasonal temperature shift from the IC clock (#1522).

    Reads ``game_clock`` for the current IC month and looks up the per-month curve.
    Returns 0 when no game clock exists yet (the shift is simply absent, not an error).
    """
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return 0
    return month_temperature_shift(ic_now.month)


def climate_exposure_base(
    climate: Climate | None,
    stat_key: StatKey,
    *,
    temperature_shift: int = 0,
) -> int:
    """A climate's contribution to one exposure axis, before local modifiers/floor (#1522).

    Decomposes the signed weights onto the floored axes, applying the seasonal shift to
    temperature first: ``temperature`` > 0 → HEAT, < 0 → COLD; ``moisture`` > 0 → WET, < 0
    → DRY. Each axis is floored at 0 (a signed weight feeds exactly one of its pair). WIND
    is never climate-driven (it comes from weather/magic), so it returns 0 here. The
    result is the per-axis *base* that the comfort cascade adds local modifiers onto
    before its own 0-floor — so a desert's HEAT base and a cooling fixture's negative HEAT
    modifier combine before flooring.
    """
    if climate is None:
        return 0
    if stat_key == StatKey.HEAT:
        return max(0, climate.temperature + temperature_shift)
    if stat_key == StatKey.COLD:
        return max(0, -(climate.temperature + temperature_shift))
    if stat_key == StatKey.WET:
        return max(0, climate.moisture)
    if stat_key == StatKey.DRY:
        return max(0, -climate.moisture)
    return 0


def _weather_modifier_source(area_pk: int) -> str:
    """The ``source`` tag for a region's weather-written cascade modifiers."""
    return f"{WEATHER_SOURCE_PREFIX}{area_pk}"


def get_effective_weather(area: Area | None) -> RegionWeatherState | None:
    """Walk up the area hierarchy to the nearest current-weather state (#1522).

    Most-specific-wins, like climate/realm. Returns None if no ancestor (or the area itself)
    holds weather.
    """
    node = area
    while node is not None:
        # Query the table rather than the cached reverse accessor: with the SharedMemoryModel
        # identity map, a queryset .delete() (clear_region_weather) doesn't evict an Area's
        # instance-cached ``weather_state``, so the accessor can return a stale, deleted row.
        state = RegionWeatherState.objects.filter(area=node).first()
        if state is not None:
            return state
        node = node.parent
    return None


def eligible_weather_types(area: Area | None) -> list[WeatherType]:
    """Automated, active weather types whose temperature band fits the region's climate (#1522).

    A type with a ``min``/``max_temperature`` is only eligible where the region's *effective*
    climate temperature (baseline + current seasonal shift) falls within the band — so blizzards
    never roll in the tropics. Types with no bounds are always eligible.
    """
    climate = get_effective_climate(area)
    temperature = (climate.temperature if climate is not None else 0) + current_temperature_shift()
    eligible: list[WeatherType] = []
    for weather_type in WeatherType.objects.filter(is_automated=True, is_active=True):
        if weather_type.min_temperature is not None and temperature < weather_type.min_temperature:
            continue
        if weather_type.max_temperature is not None and temperature > weather_type.max_temperature:
            continue
        eligible.append(weather_type)
    return eligible


def apply_weather_exposure(state: RegionWeatherState) -> None:
    """Re-materialize a region's weather as decaying source-tagged cascade modifiers (#1522).

    Deletes the region's prior weather-sourced ``LocationValueModifier`` rows, then writes one per
    ``WeatherTypeExposure`` of the current type, each decaying toward zero over
    ``WEATHER_FADE_DAYS`` (so weather softens between rolls and self-clears if the cron stalls).
    They cascade to the region's rooms and stack with the climate baseline. Idempotent.
    """
    source = _weather_modifier_source(state.area_id)
    LocationValueModifier.objects.filter(source=source, area_id=state.area_id).delete()
    for exposure in state.weather_type.exposures.all():
        change_per_day = round(-exposure.value / WEATHER_FADE_DAYS) if exposure.value else 0
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=state.area,
            key_type=KeyType.STAT,
            stat_key=exposure.stat_key,
            value=exposure.value,
            change_per_day=change_per_day,
            source=source,
        )


def roll_region_weather(
    area: Area,
    *,
    weather_type: WeatherType | None = None,
) -> RegionWeatherState | None:
    """Set (or roll) a region's current weather and re-apply its exposure modifiers (#1522).

    With ``weather_type`` given, forces it (the path the special feast-day loop uses for Eclipse /
    Moon Madness). Otherwise picks a weighted-random *automated* type eligible for the region's
    climate; returns None if none are eligible (nothing changes). Updates ``RegionWeatherState``
    and rewrites the decaying weather modifiers.
    """
    if weather_type is None:
        candidates = eligible_weather_types(area)
        if not candidates:
            return None
        weather_type = _weighted_choice(
            candidates, [max(1, c.selection_weight) for c in candidates]
        )
    state, _ = RegionWeatherState.objects.update_or_create(
        area=area, defaults={"weather_type": weather_type}
    )
    apply_weather_exposure(state)
    return state


def clear_region_weather(area: Area) -> None:
    """Remove a region's weather state and its weather-sourced exposure modifiers (#1522)."""
    LocationValueModifier.objects.filter(
        source=_weather_modifier_source(area.pk), area_id=area.pk
    ).delete()
    RegionWeatherState.objects.filter(area=area).delete()


def select_weather_emit(
    area: Area | None,
    *,
    season: Season | None = None,
    phase: TimePhase | None = None,
) -> WeatherEmit | None:
    """Pick a weighted-random atmospheric emit for a region's current weather (#1522).

    Resolves the region's effective weather, then filters its emits to those flagged for the
    current IC season *and* time-of-day phase (read from ``game_clock`` when not supplied).
    Returns None if there's no weather, no IC clock, or no matching emit. This is the *selection*
    seam; pushing the line to the room is a later slice.
    """
    state = get_effective_weather(area)
    if state is None:
        return None
    if season is None:
        season = get_ic_season()
    if phase is None:
        phase = get_ic_phase()
    if season is None or phase is None:
        return None
    emits = list(
        state.weather_type.emits.filter(**{f"in_{season.value}": True, f"at_{phase.value}": True})
    )
    if not emits:
        return None
    return _weighted_choice(emits, [max(1, emit.weight) for emit in emits])
