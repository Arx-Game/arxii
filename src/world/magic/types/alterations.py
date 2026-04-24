from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.conditions.models import ConditionInstance
    from world.magic.models import (
        MagicalAlterationEvent,
        MagicalAlterationTemplate,
        PendingAlteration,
    )


class AlterationGateError(Exception):
    """Raised when a character tries to spend advancement points while
    having unresolved Mage Scars."""

    user_message = (
        "You have an unresolved Mage Scar. "
        "Visit the alteration screen to resolve it before "
        "spending advancement points."
    )


class AlterationResolutionError(Exception):
    """Raised when condition application fails during alteration resolution."""

    user_message = (
        "The Mage Scar could not be applied due to a condition interaction. Please contact staff."
    )


@dataclass(frozen=True)
class PendingAlterationResult:
    """Result of creating or escalating a PendingAlteration."""

    pending: PendingAlteration
    created: bool  # True if new, False if escalated
    previous_tier: int | None  # Non-null if escalated


@dataclass(frozen=True)
class AlterationResolutionResult:
    """Result of resolving a PendingAlteration."""

    pending: PendingAlteration
    template: MagicalAlterationTemplate
    condition_instance: ConditionInstance
    event: MagicalAlterationEvent


@dataclass(frozen=True)
class PendingAlterationTierReduction:
    """Result of reduce_pending_alteration_tier (Scope 6 §7).

    Distinct from AlterationResolutionResult: no template or condition is
    created — the debt is decremented or cleared without authoring an alteration.
    """

    pending: PendingAlteration
    previous_tier: int
    new_tier: int
    resolved: bool
