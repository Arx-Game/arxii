"""The rally social verb."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import (
    ENTITY_TYPE_PC,
    CombatAllegiance,
    CombatManeuver,
    OpponentStatus,
    ParticipantStatus,
    SurgeTriggerKind,
)
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.declarations.social_check import roll_social_check
from world.combat.surge_rolls import apply_rolled_surge, persona_name_of, surge_tuning_for
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.combat.models import SurgeTuning
    from world.traits.models import CheckOutcome


def declare_rally(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a rallying maneuver — inspire an ally, auto-ready (#2015).

    RALLY rolls a presence/Performance check at round-tick; on success it applies
    a short-lived ``Inspired`` condition to the ally (a damage-multiplier buff) and,
    on a great success, restores morale to ally-side summon opponents. This
    function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot rally: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot rally: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot rally: character is dead."
        raise ValueError(msg)

    if ally.pk == participant.pk:
        msg = "Cannot rally yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Rally target must be an active participant in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.RALLY,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _surge_rallied_ally(
    rallier: CombatParticipant,
    ally: CombatParticipant,
    rally_outcome: CheckOutcome | None,
    tuning: SurgeTuning | None,
    difficulty: int,
) -> None:
    """The rallied ally's surge, banded by the Rally roll's outcome (#4737).

    A quiet no-op for an ally who left the encounter or died since the declaration.
    ``difficulty`` is the fixed rally difficulty the roll was made against, shown on the
    roll line; ``tuning`` is the already-read ``SurgeTuning`` (None looks it up).
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    if ally.status != ParticipantStatus.ACTIVE or is_dead(ally.character_sheet):
        return
    apply_rolled_surge(
        encounter=rallier.encounter,
        participant=ally,
        trigger_kind=SurgeTriggerKind.RALLIED,
        outcome=rally_outcome,
        potency=difficulty,
        subject_sheet=rallier.character_sheet,
        source_character=rallier.character_sheet.character,
        tuning=tuning,
        cause=f"{persona_name_of(rallier)} rallies {persona_name_of(ally)}.",
    )


def _resolve_rally(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared rally — inspire an ally (#2015).

    Rolls the Rally check (presence + Performance + Oratory). On success, applies
    a short-lived ``Inspired`` condition to the ally. On a great success (SL>=3),
    also restores morale to ally-side summon opponents.

    Whatever the roll, the ally then gets a rolled surge (#4737): the Rally check's outcome
    picks the band, so a better rally never surges the ally less. When staff authored a
    ``RALLIED`` ``SurgeTuning``, the check it names is the one rolled; without one the
    Rally check type is found by name, as before.
    """
    from world.combat.constants import (  # noqa: PLC0415
        RALLY_BASE_DIFFICULTY,
        RALLY_GREAT_SUCCESS_LEVEL,
        RALLY_MORALE_PER_LEVEL,
    )
    from world.combat.social_combat_content import INSPIRED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    from world.checks.models import CheckType  # noqa: PLC0415

    surge_tuning = surge_tuning_for(SurgeTriggerKind.RALLIED, warn=False)
    rally_check = (
        surge_tuning.check_type
        if surge_tuning is not None
        else CheckType.objects.filter(name="Rally", is_active=True).first()
    )
    rally_result = (
        None
        if rally_check is None
        else roll_social_check(participant, rally_check, RALLY_BASE_DIFFICULTY)
    )
    success_level = (rally_result.success_level or 0) if rally_result is not None else 0
    ally = action.focused_ally_target
    if success_level >= 1 and ally is not None:
        # Apply Inspired condition to the ally.
        inspired = ConditionTemplate.objects.filter(name=INSPIRED_CONDITION_NAME).first()
        if inspired is not None:
            apply_condition(
                ally.character_sheet.character,
                inspired,
                source_character=participant.character_sheet.character,
                source_description="Rallied in combat.",
            )

        # Great success: restore morale to ally-side summon opponents.
        if success_level >= RALLY_GREAT_SUCCESS_LEVEL:
            from world.covenants.services import (  # noqa: PLC0415
                covenant_role_action_scaling_bonus,
            )

            # A rally scaling bonus increases the morale restored by the
            # success level, matching the additive effect scaling used by
            # other universal combat actions such as interpose.
            bonus = covenant_role_action_scaling_bonus(
                participant.character_sheet.character, "combat_rally"
            )
            restore = int(success_level * RALLY_MORALE_PER_LEVEL * (1 + bonus))
            ally_summons = CombatOpponent.objects.filter(
                encounter=participant.encounter,
                status=OpponentStatus.ACTIVE,
                allegiance=CombatAllegiance.ALLY,
            )
            for opp in ally_summons:
                opp.morale = min(opp.max_morale, opp.morale + restore)
                opp.save(update_fields=["morale"])

    if rally_result is not None and ally is not None:
        _surge_rallied_ally(
            participant, ally, rally_result.outcome, surge_tuning, RALLY_BASE_DIFFICULTY
        )

    return outcome
