"""Probing an opponent."""

from __future__ import annotations

from world.combat.models import CombatOpponent


def increment_probing(opponent: CombatOpponent, amount: int) -> None:
    """Add ``amount`` to an opponent's probing counter (clamped at zero) and persist.

    Single standalone write path for ``probing_current`` used by combo-opening
    passives so probing feeds combo detection identically to damage-sourced probing.
    """
    opponent.probing_current = max(0, opponent.probing_current + amount)
    opponent.save(update_fields=["probing_current"])
