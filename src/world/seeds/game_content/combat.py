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
    from world.combat.models import FleeConfig
    from world.conditions.models import PenetrationOutcomeFactor
    from world.mechanics.models import ModifierTarget


@dataclass
class PenetrationContestResult:
    """Returned by seed_penetration_contest()."""

    check_type: CheckType
    factors: list[PenetrationOutcomeFactor]
    modifier_target: ModifierTarget


@dataclass
class FleeSeedResult:
    """Returned by seed_flee_check()."""

    check_type: CheckType
    modifier_target: ModifierTarget
    config: FleeConfig


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


def seed_flee_check() -> FleeSeedResult:
    """Seed the #878 flee check for production play.

    Composes the three flee wire functions: the trait-weighted ``flee``
    CheckType (agility 1.00 / wits 0.50), the check-scoped ``flee``
    ModifierTarget for character-side buffs, and the FleeConfig singleton
    with tier modifiers and starter consequence pool. Idempotent — re-runs
    are no-ops and staff edits to existing rows are preserved.
    """
    from world.combat.factories import (  # noqa: PLC0415
        wire_flee_check_type,
        wire_flee_config,
        wire_flee_modifier_target,
    )

    # Capture the CheckType for the result; wire_flee_modifier_target() and
    # wire_flee_config() call wire_flee_check_type() internally (idempotent).
    check_type = wire_flee_check_type()
    modifier_target = wire_flee_modifier_target()
    config = wire_flee_config()
    return FleeSeedResult(
        check_type=check_type,
        modifier_target=modifier_target,
        config=config,
    )


def seed_encounter_beat_wiring() -> None:
    """Seed the ENCOUNTER_COMPLETED → beat TriggerDefinition (#1746).

    Creates (get_or_create) the ``encounter_completed_beat_wiring`` FlowDefinition
    (one CALL_SERVICE_FUNCTION step → encounter_completed_beat_handler) and its
    TriggerDefinition. Idempotent — re-runs are no-ops and staff edits to existing
    rows are preserved. The per-room Trigger is installed lazily at encounter
    completion by ``install_encounter_beat_trigger``.
    """
    from world.combat.beat_wiring import wire_encounter_beat_triggers  # noqa: PLC0415

    wire_encounter_beat_triggers()
