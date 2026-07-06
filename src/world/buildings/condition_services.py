"""Condition recovery + preparation services (#1930).

The player-facing loops around the condition-tier ladder:

* ``settle_upkeep_arrears`` — pay the bounded owed amount down to zero.
* ``refurbish_building`` — priced restore to EXCELLENT (the fast path;
  weekly paid upkeep is the slow one). Requires arrears settled first.
  ("Refurbish", not "renovate" — a *renovation* is the existing
  BUILDING_RENOVATION kind-swap project; see AGENT_GLOSSARY.md.)
* ``prepare_building`` — the cleaning/party-preparation fiction: pushes
  one tier ABOVE normal (EXCELLENT → EXTRAVAGANT → IMMACULATE) for a
  gala window; above-normal tiers dwell-decay back (see
  ``upkeep_services``). A deliberate luxury spend.
* ``set_ultra_upkeep`` — owner toggle for the premium that holds
  IMMACULATE past its dwell.

All charges are pure sinks through the audited currency ledger (#923).
Costs are PLACEHOLDER, scaled by ``Building.target_size``. Insufficient
funds surface as ``django.core.exceptions.ValidationError`` (raised
before any state write), matching the station-repair precedent; refusals
raise ``ConditionServiceError`` with a player-safe ``user_message``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from world.buildings.constants import (
    PREPARE_COPPER_COST_EXTRAVAGANT,
    PREPARE_COPPER_COST_IMMACULATE,
    REFURBISH_COPPER_PER_TIER,
    ConditionTier,
)
from world.buildings.upkeep_services import set_condition_tier

if TYPE_CHECKING:
    from world.buildings.models import Building
    from world.currency.models import CharacterPurse

logger = logging.getLogger(__name__)

_PREPARE_COST_BY_TARGET_TIER: dict[int, int] = {
    ConditionTier.EXTRAVAGANT: PREPARE_COPPER_COST_EXTRAVAGANT,
    ConditionTier.IMMACULATE: PREPARE_COPPER_COST_IMMACULATE,
}


class ConditionServiceError(Exception):
    """A condition-service refusal, carrying a player-safe message."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


def _sink(purse: CharacterPurse, amount: int, reason: str) -> None:
    from world.currency.services import transfer  # noqa: PLC0415

    transfer(amount=amount, reason=reason, from_purse=purse)


def _require_settled(building: Building, verb: str) -> None:
    if building.upkeep_arrears > 0:
        msg = f"building {building.pk} has {building.upkeep_arrears} arrears; {verb} refused"
        raise ConditionServiceError(
            msg,
            user_message="Outstanding upkeep must be settled first.",
        )


def refurbish_cost(building: Building) -> int:
    """Coppers to restore ``building`` to EXCELLENT (0 when already there)."""
    deficit = max(0, ConditionTier.EXCELLENT - building.condition_tier)
    return REFURBISH_COPPER_PER_TIER * deficit * building.target_size


def prepare_cost(building: Building) -> int:
    """Coppers for the next preparation step above the current tier.

    Raises ``ConditionServiceError`` when the building isn't eligible
    (below EXCELLENT, or already IMMACULATE).
    """
    target = building.condition_tier + 1
    if building.condition_tier < ConditionTier.EXCELLENT:
        msg = f"building {building.pk} below EXCELLENT; preparation refused"
        raise ConditionServiceError(
            msg,
            user_message="The building must be in excellent condition before it can be "
            "specially prepared — refurbish it first.",
        )
    if target > ConditionTier.IMMACULATE:
        msg = f"building {building.pk} already at IMMACULATE"
        raise ConditionServiceError(
            msg,
            user_message="The building is already immaculately prepared.",
        )
    return _PREPARE_COST_BY_TARGET_TIER[target] * building.target_size


@transaction.atomic
def settle_upkeep_arrears(*, building: Building, payer_purse: CharacterPurse) -> int:
    """Pay ``building.upkeep_arrears`` down to zero. Returns the amount paid.

    Raises ``ValidationError`` (from ``transfer``) on insufficient funds;
    arrears are unchanged in that case. Returns 0 when nothing is owed.
    """
    owed = building.upkeep_arrears
    if owed <= 0:
        return 0
    _sink(payer_purse, owed, f"upkeep arrears: building {building.pk}")
    building.upkeep_arrears = 0
    building.save(update_fields=["upkeep_arrears"])
    return owed


@transaction.atomic
def refurbish_building(*, building: Building, payer_purse: CharacterPurse) -> int:
    """Restore ``building`` to EXCELLENT for coppers. Returns the cost paid.

    Aspiration-shaped recovery: one priced action back to normal — no
    repair-chore treadmill. Requires arrears settled; refuses when the
    building is already at or above EXCELLENT.
    """
    _require_settled(building, "refurbish")
    if building.condition_tier >= ConditionTier.EXCELLENT:
        msg = f"building {building.pk} already at/above EXCELLENT"
        raise ConditionServiceError(
            msg,
            user_message="The building is already in excellent condition.",
        )
    cost = refurbish_cost(building)
    _sink(payer_purse, cost, f"refurbishment: building {building.pk}")
    building.consecutive_missed_upkeep = 0
    building.consecutive_paid_upkeep = 0
    building.save(update_fields=["consecutive_missed_upkeep", "consecutive_paid_upkeep"])
    set_condition_tier(building, ConditionTier.EXCELLENT)
    return cost


@transaction.atomic
def prepare_building(*, building: Building, payer_purse: CharacterPurse) -> int:
    """Push ``building`` one tier above normal (gala preparation). Returns the new tier.

    EXCELLENT → EXTRAVAGANT → IMMACULATE, one step per (increasingly
    steep) application. Requires arrears settled. The shine is temporary:
    above-normal tiers dwell-decay back unless IMMACULATE is held via
    ultra upkeep.
    """
    _require_settled(building, "preparation")
    cost = prepare_cost(building)
    target = building.condition_tier + 1
    _sink(payer_purse, cost, f"grand preparation: building {building.pk}")
    set_condition_tier(building, target)
    return target


def set_ultra_upkeep(*, building: Building, enabled: bool) -> None:
    """Toggle the ultra-upkeep premium that holds IMMACULATE past its dwell."""
    if building.ultra_upkeep == enabled:
        return
    building.ultra_upkeep = enabled
    building.save(update_fields=["ultra_upkeep"])
