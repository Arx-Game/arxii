"""The rally social verb."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import (
    ENTITY_TYPE_PC,
    CombatAllegiance,
    CombatManeuver,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.declarations.social_check import _resolve_social_check
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    pass


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


def _resolve_rally(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared rally — inspire an ally (#2015).

    Rolls the Rally check (presence + Performance + Oratory). On success, applies
    a short-lived ``Inspired`` condition to the ally. On a great success (SL>=3),
    also restores morale to ally-side summon opponents.
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

    rally_check = CheckType.objects.filter(name="Rally", is_active=True).first()
    success_level = (
        0
        if rally_check is None
        else _resolve_social_check(participant, rally_check, RALLY_BASE_DIFFICULTY)
    )
    if success_level >= 1:
        ally = action.focused_ally_target
        if ally is not None:
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

    return outcome
