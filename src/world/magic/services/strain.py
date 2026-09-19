"""Shared strain conversion and commitment helpers.

The strain curve is authored by the combat ``StrainConfig`` singleton but is
used by both ordinary technique casts and clash contributions.
"""

from __future__ import annotations

from typing import Protocol


class StrainCurve(Protocol):
    """The authored fields required by the strain conversion curve."""

    conversion_base: int
    diminishing_step: int
    diminishing_floor: int


def strain_to_intensity(*, strain_commitment: int, config: StrainCurve) -> int:
    """Convert committed anima into a diminishing-return power bonus.

    Args:
        strain_commitment: Non-negative anima committed to the push.
        config: Authored curve values, normally ``StrainConfig``.

    Returns:
        The deterministic bonus to add to technique power.
    """
    remaining = max(strain_commitment, 0)
    bonus = 0
    rate = config.conversion_base
    step = max(config.diminishing_step, 1)
    while remaining > 0:
        take = min(remaining, step)
        bonus += take * rate
        remaining -= take
        rate = max(rate - 1, config.diminishing_floor)
    return bonus
