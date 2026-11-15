"""The one development point cost curve every levelling trait shares (#5093).

A trait value ``v`` sits in character level ``v // DP_STEPS_PER_BAND``, its band. A band costs
``base_cost × (growth_percent / 100) ^ (band - start_level)`` development points, read from
the :class:`DevelopmentCostConfig` row, and every one of the band's ten steps costs a tenth of
that. A step counts in the band of its starting value, so 39 to 40 costs what 30 to 31 does.
Skills, specializations and threads all read these functions; a thread multiplies a step by
its kind's ``imbue_cost_multiplier`` on top.
"""

from __future__ import annotations

from fractions import Fraction

from world.progression.constants import DP_BASE_LEVEL, DP_STEPS_PER_BAND
from world.progression.models.dev_cost_config import DevelopmentCostConfig


def _band_cost(config: DevelopmentCostConfig, band: int) -> int:
    """Development points one whole band costs, from an already-loaded config row."""
    if band <= config.start_level:
        return config.base_cost
    # Exact rational arithmetic: a float power drifts in the deep bands.
    grown = Fraction(config.growth_percent, 100) ** (band - config.start_level)
    return round(config.base_cost * grown)


def _step_cost(config: DevelopmentCostConfig, band: int) -> int:
    """Development points one step inside ``band`` costs, never less than 1."""
    return max(_band_cost(config, band) // DP_STEPS_PER_BAND, 1)


def dp_cost_for_band(band: int) -> int:
    """Development points one whole character-level band costs on the shared curve."""
    return _band_cost(DevelopmentCostConfig.get_singleton(), band)


def dp_cost_for_step(value: int) -> int:
    """Development points the step from ``value`` to ``value + 1`` costs (minimum 1).

    A step counts in the band of its starting value, so every step in one band costs the same
    and a step that starts in the next band costs one growth step more.
    """
    return _step_cost(DevelopmentCostConfig.get_singleton(), value // DP_STEPS_PER_BAND)


def cumulative_dp_for_level(value: int) -> int:
    """Total development points needed to reach ``value`` from the base level of 10.

    The sum of the step costs from ``DP_BASE_LEVEL`` up to ``value - 1``. At or below the base
    level (a character-creation starting value) it is 0.
    """
    if value <= DP_BASE_LEVEL:
        return 0
    config = DevelopmentCostConfig.get_singleton()
    total = 0
    step = DP_BASE_LEVEL
    while step < value:
        band = step // DP_STEPS_PER_BAND
        band_end = min((band + 1) * DP_STEPS_PER_BAND, value)
        total += (band_end - step) * _step_cost(config, band)
        step = band_end
    return total
