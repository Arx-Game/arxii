"""Plain dataclasses for the ships system (#1832)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.conditions.models import CapabilityType


@dataclass(frozen=True)
class ShipStatBonus:
    """A bundle of stat bonuses a ship's upgrades/condition contribute.

    Produced by ship stat-resolution helpers (added in later #1832 tasks) so
    callers get a typed, immutable result instead of a dict.
    """

    hull: int = 0
    handling: int = 0
    armament: int = 0


@dataclass(frozen=True)
class ShipCapabilityGrant:
    """One capability a ship's sanctum confers, already resolved to a magnitude (#2736).

    ``value`` sits on the ADR-0164 capability ladder: the authored
    ``ThreadPullEffect.capability_grant_value`` after ``apply_capability_curve``. The
    caller's only job is to write it onto the ship's military unit — resolving *which*
    capability at *what* magnitude belongs with the sanctum, in ``sanctum_bonus.py``,
    not in the battle bridge.
    """

    capability: CapabilityType
    value: int
