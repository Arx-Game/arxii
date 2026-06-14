"""Type definitions for the items app."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.mechanics.types import AppliedEffect


@dataclass(frozen=True)
class UseItemResult:
    """Outcome of using an item: effects applied, charges left, destruction."""

    applied_effects: list[AppliedEffect] = field(default_factory=list)
    charges_remaining: int = 0
    destroyed: bool = False
    soft_deleted: bool = False
    check_result: CheckResult | None = None
