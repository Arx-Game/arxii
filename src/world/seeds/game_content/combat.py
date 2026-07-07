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


def seed_dramatic_surge_content() -> None:
    """Seed the dramatic surge engine's default content (#2013).

    Idempotent (get_or_create at every layer). Creates:
    - the FIRST production RelationshipTrack rows this codebase ships:
      "Bond" (POSITIVE), "Rivalry" / "Enemies" (NEGATIVE) — all
      fuels_escalation_spikes=True. Without the negative tracks the
      hated-foe leg is content-dead.
    - a default "Standard Dramatic Escalation" EscalationCurve.
    - StakesEscalationModifier rows for all five StakesLevel values;
      REGIONAL and above carry the default curve + increasing bonuses
      (staff-tunable from here via admin).
    - the escalation spike TriggerDefinitions (wire_escalation_content).
    """
    from world.combat.constants import StakesLevel  # noqa: PLC0415
    from world.combat.factories import (  # noqa: PLC0415
        ensure_escalation_pace_check_type,
        wire_escalation_content,
    )
    from world.combat.models import EscalationCurve, StakesEscalationModifier  # noqa: PLC0415
    from world.relationships.constants import TrackSign  # noqa: PLC0415
    from world.relationships.models import RelationshipTrack  # noqa: PLC0415

    wire_escalation_content()

    RelationshipTrack.objects.get_or_create(
        name="Bond",
        defaults={
            "slug": "bond",
            "description": "A deep, protective attachment between characters.",
            "sign": TrackSign.POSITIVE,
            "display_order": 10,
            "fuels_escalation_spikes": True,
        },
    )
    RelationshipTrack.objects.get_or_create(
        name="Rivalry",
        defaults={
            "slug": "rivalry",
            "description": "Competitive antagonism — a foe you measure yourself against.",
            "sign": TrackSign.NEGATIVE,
            "display_order": 20,
            "fuels_escalation_spikes": True,
        },
    )
    RelationshipTrack.objects.get_or_create(
        name="Enemies",
        defaults={
            "slug": "enemies",
            "description": "Open, active hostility.",
            "sign": TrackSign.NEGATIVE,
            "display_order": 21,
            "fuels_escalation_spikes": True,
        },
    )

    pace_check_type = ensure_escalation_pace_check_type()
    curve, _ = EscalationCurve.objects.get_or_create(
        name="Standard Dramatic Escalation",
        defaults={
            "description": "Default escalating ramp for stakes-driven encounters.",
            "start_round": 2,
            "intensity_step": 1,
            "pace_check_type": pace_check_type,
            "spike_intensity_amount": 3,
            "spike_minimum_track_points": 5,
            "peril_spike_intensity_amount": 4,
            "hated_foe_spike_intensity_amount": 4,
            "surge_narration": "{character}'s power surges with sudden, dramatic force.",
        },
    )

    StakesEscalationModifier.objects.get_or_create(
        stakes_level=StakesLevel.LOCAL,
        defaults={"intensity_step_bonus": 0, "initial_surge": 0, "default_curve": None},
    )
    StakesEscalationModifier.objects.get_or_create(
        stakes_level=StakesLevel.REGIONAL,
        defaults={"intensity_step_bonus": 1, "initial_surge": 2, "default_curve": curve},
    )
    StakesEscalationModifier.objects.get_or_create(
        stakes_level=StakesLevel.NATIONAL,
        defaults={"intensity_step_bonus": 2, "initial_surge": 3, "default_curve": curve},
    )
    StakesEscalationModifier.objects.get_or_create(
        stakes_level=StakesLevel.CONTINENTAL,
        defaults={"intensity_step_bonus": 3, "initial_surge": 4, "default_curve": curve},
    )
    StakesEscalationModifier.objects.get_or_create(
        stakes_level=StakesLevel.WORLD,
        defaults={"intensity_step_bonus": 4, "initial_surge": 5, "default_curve": curve},
    )
