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

from typing import TYPE_CHECKING

from world.game_clock.services import get_ic_now
from world.locations.constants import StatKey
from world.weather.constants import MONTH_TEMPERATURE_SHIFT

if TYPE_CHECKING:
    from datetime import datetime

    from world.areas.models import Area
    from world.weather.models import Climate


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
