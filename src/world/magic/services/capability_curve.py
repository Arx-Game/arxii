"""Geometric capability magnitude curve (#2708).

Capability values live on the ADR-0164 ladder, whose tier anchors (5 mortal, ~10
gifted, 25 greater supernatural, 100 mythic) are roughly geometric. Power therefore
*multiplies* a capability rather than adding to it, so drawing on real power moves a
character a tier up the ladder instead of a few points along it.

Deliberately NOT folded into ``_scale_by_power_and_sl``
(``world/magic/models/techniques.py``): that helper is strictly linear and serves
severity, duration, and damage, none of which are changing shape.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import CapabilityPowerConfig


def get_capability_power_config() -> CapabilityPowerConfig | None:
    """Return the CapabilityPowerConfig singleton, or None if no row exists yet."""
    from world.magic.models import CapabilityPowerConfig  # noqa: PLC0415

    return CapabilityPowerConfig.objects.filter(pk=1).first()


def apply_capability_curve(base: int, *, power: int, sensitivity: Decimal) -> int:
    """Return ``base`` curved geometrically by ``power``.

        value = round(base * 2 ** (sensitivity * power / power_per_doubling))

    Returns ``base`` unchanged when the curve is disabled (no config row), when
    ``sensitivity`` is 0 (the authored default — a grant opts in to scaling), when
    ``power`` is non-positive, or when the config row's ``power_per_doubling`` is
    non-positive (a `MinValueValidator(1)` blocks this on new writes, but a
    pre-existing row or a path that bypasses `full_clean()` could still carry a
    stale 0 — degrade to disabled rather than raising `DivisionByZero`). Never
    returns less than ``base``: power is an empowerment axis, and impairment is
    the conditions layer's job (a negative ``ConditionCapabilityEffect``), not
    this curve's.
    """
    config = get_capability_power_config()
    if config is None or sensitivity <= 0 or power <= 0 or config.power_per_doubling <= 0:
        return base
    exponent = (sensitivity * Decimal(power)) / Decimal(config.power_per_doubling)
    return round(base * Decimal(2) ** exponent)
