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

    RALLY rolls the RALLIED surge tuning's check at round-tick; on success it applies
    the designated short-lived ``Inspired`` condition to the ally (a damage-multiplier buff) and,
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

    The band's intensity is scaled by the rallier's Rally surge intensity (the maneuver
    effect catalog, #4783: a percentage, base 100, plus the rallier's own modifiers such as
    a vow stat scaling row); the band's control change and condition are not scaled. When
    the scale is above 100% the roll line notes the extra intensity as ``surge +N``.
    """
    from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
    from world.mechanics.effect_targets import effect_value  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    if ally.status != ParticipantStatus.ACTIVE or is_dead(ally.character_sheet):
        return
    rallier_character = rallier.character_sheet.character
    intensity_scale = (
        effect_value(rallier.character_sheet, ManeuverEffectKey.RALLY_SURGE_INTENSITY) / 100
    )
    apply_rolled_surge(
        encounter=rallier.encounter,
        participant=ally,
        trigger_kind=SurgeTriggerKind.RALLIED,
        outcome=rally_outcome,
        potency=difficulty,
        subject_sheet=rallier.character_sheet,
        intensity_scale=intensity_scale,
        source_character=rallier_character,
        tuning=tuning,
        cause=f"{persona_name_of(rallier)} rallies {persona_name_of(ally)}.",
        vow_scaled=intensity_scale != 1,
    )


def _grant_free_dig_deeps(rallier: CombatParticipant, ally: CombatParticipant) -> None:
    """A successful Rally gives the ally free dig deeps, and tells her (#4738).

    The count is ``StrainConfig.free_dig_deeps_per_encouragement``. A quiet no-op for an ally
    with no combat engagement here or when the count is 0.

    The grant, the cached engagement and the message all wait for the round's transaction
    to commit (``transaction.on_commit``). The round resolves inside one atomic block, and a
    round that rolls back would leave the identity-mapped engagement holding a free dig deep
    the database never kept; written after the commit, nothing is there to undo and a player
    never sees or spends a free dig deep the database does not hold.
    """
    from django.db import transaction  # noqa: PLC0415

    from world.combat.dig_deep import combat_engagement_of, grant_free_dig_deeps  # noqa: PLC0415
    from world.combat.services.encounter.config import get_strain_config  # noqa: PLC0415

    count = get_strain_config().free_dig_deeps_per_encouragement
    if count <= 0:
        return
    giver_sheet = rallier.character_sheet
    giver_name = persona_name_of(rallier)

    def _grant() -> None:
        engagement = combat_engagement_of(ally)
        if engagement is None:
            return
        grant_free_dig_deeps(engagement, count, giver_sheet)
        noun = "a free dig deep" if count == 1 else f"{count} free dig deeps"
        ally.character_sheet.character.msg(f"{giver_name}'s encouragement gives you {noun}.")

    transaction.on_commit(_grant)


def _resolve_rally(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared rally — inspire an ally (#2015).

    Rolls the check the ``RALLIED`` ``SurgeTuning`` names (#4737, #4739). With no such
    tuning nothing is rolled and nothing happens; the Required content dashboard lists the
    missing tuning. On success, applies the condition ``SocialManeuverConfig``
    designates as Rally's success condition (Inspired) to the ally. On a great success
    (SL>=3), also restores morale to ally-side summon opponents: success level x the
    rallier's Rally morale (the maneuver effect catalog, #4783).

    Whatever the roll, the ally then gets a rolled surge (#4737): the Rally check's outcome
    picks the band, so a better rally never surges the ally less.
    """
    from world.combat.constants import (  # noqa: PLC0415
        RALLY_BASE_DIFFICULTY,
        RALLY_GREAT_SUCCESS_LEVEL,
    )
    from world.combat.services.encounter.config import (  # noqa: PLC0415
        get_social_maneuver_config,
    )
    from world.conditions.services import apply_condition  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    surge_tuning = surge_tuning_for(SurgeTriggerKind.RALLIED, warn=False)
    # An inactive check type counts as unset, the same rule Taunt follows.
    if surge_tuning is None or not surge_tuning.check_type.is_active:
        return outcome
    rally_result = roll_social_check(participant, surge_tuning.check_type, RALLY_BASE_DIFFICULTY)
    success_level = rally_result.success_level or 0
    ally = action.focused_ally_target
    if success_level >= 1 and ally is not None:
        # Apply the designated success condition (Inspired) to the ally.
        inspired = get_social_maneuver_config().rally_success_condition
        if inspired is not None:
            apply_condition(
                ally.character_sheet.character,
                inspired,
                source_character=participant.character_sheet.character,
                source_description="Rallied in combat.",
            )

        _grant_free_dig_deeps(participant, ally)

        # Great success: restore morale to ally-side summon opponents.
        if success_level >= RALLY_GREAT_SUCCESS_LEVEL:
            from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
            from world.mechanics.effect_targets import effect_value  # noqa: PLC0415

            # Each success level restores the rallier's Rally morale (the maneuver effect
            # catalog, #4783: base 15, plus the rallier's own modifiers).
            restore = success_level * effect_value(
                participant.character_sheet, ManeuverEffectKey.RALLY_MORALE
            )
            ally_summons = CombatOpponent.objects.filter(
                encounter=participant.encounter,
                status=OpponentStatus.ACTIVE,
                allegiance=CombatAllegiance.ALLY,
            )
            for opp in ally_summons:
                opp.morale = min(opp.max_morale, opp.morale + restore)
                opp.save(update_fields=["morale"])

    if ally is not None:
        _surge_rallied_ally(
            participant, ally, rally_result.outcome, surge_tuning, RALLY_BASE_DIFFICULTY
        )

    return outcome
