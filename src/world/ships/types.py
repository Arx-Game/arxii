"""Plain dataclasses for the ships system (#1832)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShipStatBonus:
    """A bundle of stat bonuses a ship's upgrades/condition contribute.

    Produced by ship stat-resolution helpers (added in later #1832 tasks) so
    callers get a typed, immutable result instead of a dict.
    """

    hull: int = 0
    handling: int = 0
    armament: int = 0
