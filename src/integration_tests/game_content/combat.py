"""CombatContent — seed orchestrators for combat-cluster game content.

First combat game-content module (the 2026-04-26 seed audit flags the gap).
Like the magic seeders, everything here is create-if-missing and doubles as
integration-test setup and (via seed_magic_dev → future ``arx seed dev``)
production seed data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.conditions.models import PenetrationOutcomeFactor
    from world.mechanics.models import ModifierTarget


@dataclass
class PenetrationContestResult:
    """Returned by seed_penetration_contest()."""

    check_type: CheckType
    factors: list[PenetrationOutcomeFactor]
    modifier_target: ModifierTarget


def seed_penetration_contest() -> PenetrationContestResult:
    """Seed the #639 penetration contest for production play (#767).

    Composes the three penetration wire functions: the trait-weighted
    ``penetration`` CheckType, the four-rung PenetrationOutcomeFactor ladder
    (bounce / partial / clean / overpenetration), and the check-scoped
    ``penetration`` ModifierTarget for caster-side buffs. Idempotent —
    re-runs are no-ops and staff edits to existing rows are preserved.
    """
    from world.combat.factories import (  # noqa: PLC0415
        wire_penetration_check_type,
        wire_penetration_modifier_target,
    )
    from world.conditions.factories import wire_penetration_factors  # noqa: PLC0415

    # Capture the CheckType for the result; wire_penetration_modifier_target()
    # calls this again internally (idempotent, same instance returned).
    check_type = wire_penetration_check_type()
    modifier_target = wire_penetration_modifier_target()
    return PenetrationContestResult(
        check_type=check_type,
        factors=wire_penetration_factors(),
        modifier_target=modifier_target,
    )
