"""The parley social verb and its gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import (
    BOSS_PARLEY_RESISTANCE_STEP,
    ENTITY_TYPE_PC,
    CombatManeuver,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.declarations.social_check import _social_verb_success_level
from world.combat.types import ActionOutcome
from world.conditions.constants import Allegiance
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    pass


def _parley_gate_met(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> bool:
    """Return whether parley's precondition is met (#2015).

    Parley is gated: the opponent must be faltering or broken (morale below
    ``FALTER_MORALE_THRESHOLD``), OR the participant's persona must hold an
    ``NPCStanding`` with ``affection >= PARLEY_DISPOSITION_FLOOR`` toward the
    opponent's persona. A steady, unknown opponent cannot be parleyed with —
    but mindless targets are not rejected here (they roll with resistance at
    resolve time; a breakthrough grants a fleeting mind).
    """
    from world.combat.constants import PARLEY_DISPOSITION_FLOOR  # noqa: PLC0415
    from world.combat.morale import OpponentMoraleState, morale_state_for  # noqa: PLC0415

    if morale_state_for(opponent) != OpponentMoraleState.STEADY:
        return True

    # Steady opponent: check durable standing toward the opponent's persona.
    if opponent.persona_id is None:
        return False

    from world.npc_services.models import NPCStanding  # noqa: PLC0415
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        pc_persona = persona_for_character(participant.character_sheet.character)
    except MissingPrimaryPersonaError:
        # Half-set-up actor with no primary persona — no standing to check.
        return False

    return NPCStanding.objects.filter(
        persona=pc_persona,
        npc_persona_id=opponent.persona_id,
        affection__gte=PARLEY_DISPOSITION_FLOOR,
    ).exists()


def declare_parley(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a parley maneuver — talk a foe down mid-fight, auto-ready (#2015).

    PARLEY is gated (see ``_parley_gate_met``): the opponent must be faltering/
    broken or the participant must hold sufficient standing. At round-tick it
    rolls a charm/Persuasion(Seduction) check against the target's Composure; on
    success it routes through ``apply_social_disposition_delta`` and, on a
    decisive success, calms the opponent (Calm condition → NEUTRAL allegiance).
    This function only records the declaration.
    """
    from world.combat.berserk_compulsion import reject_if_berserk  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    reject_if_berserk(participant, "parley")
    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot parley: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot parley: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot parley: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Parley target must be an active opponent in this encounter."
        raise ValueError(msg)

    if not _parley_gate_met(participant, opponent):
        msg = (
            "Cannot parley: the opponent's nerve is steady and you hold no "
            "standing with them. Break their resolve first, or build rapport."
        )
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.PARLEY,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _resolve_parley(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared parley — talk a foe down mid-fight (#2015).

    Rolls the Parley check (charm + Persuasion + Seduction) against the target's
    Composure (+ mindless resistance — a breakthrough grants a fleeting mind). On
    success, routes through ``apply_social_disposition_delta_for_level``. On a decisive
    success (SL>=3), calms the opponent. On a critical success (SL>=5) against a
    broken opponent, the NPC yields (FLED).
    """
    from world.combat.constants import (  # noqa: PLC0415
        PARLEY_CRITICAL_SUCCESS_LEVEL,
        PARLEY_DECISIVE_SUCCESS_LEVEL,
        OpponentStatus,
    )
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
        tier_has_morale,
    )
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.npc_services.social_disposition import (  # noqa: PLC0415
        apply_social_disposition_delta_for_level,
    )

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is None:
        return outcome

    success_level = _social_verb_success_level(participant, "Parley", action, target)

    if success_level < 1:
        # Failed: mindless targets narrate "it has no mind to reach."
        if not tier_has_morale(target):
            outcome.summary = "It has no mind to reach."
        return outcome

    # Success: apply the disposition delta (the built path, now reachable in combat).
    actor = participant.character_sheet.character
    target_persona_id = target.persona_id
    if target_persona_id is not None:
        apply_social_disposition_delta_for_level(actor, target_persona_id, success_level)

    # Decisive success: calm the opponent (Calm condition -> NEUTRAL allegiance).
    # Boss sway resistance (#2642): a BOSS-tier opponent resists — it requires
    # one success-level step above the normal decisive threshold. Court-tier
    # NPCs (the majority) calm at the unmodified threshold.
    required_decisive_level = PARLEY_DECISIVE_SUCCESS_LEVEL
    if target.tier == OpponentTier.BOSS:
        required_decisive_level += BOSS_PARLEY_RESISTANCE_STEP
    if success_level >= required_decisive_level and target.objectdb is not None:
        # Designated by field, never by name (#4091 final review): the calming
        # condition is the one that sets NEUTRAL; lowest pk when staff author several.
        # The REQUIRED dashboard probe `allegiance-calm-condition` reports none.
        calm = (
            ConditionTemplate.objects.filter(sets_allegiance=Allegiance.NEUTRAL)
            .order_by("pk")
            .first()
        )
        if calm is not None:
            apply_condition(
                target.objectdb,
                calm,
                source_character=actor,
                source_description="Parleyed into calm.",
            )

    # Critical success against a broken opponent: the NPC yields (FLED, alive).
    if (
        success_level >= PARLEY_CRITICAL_SUCCESS_LEVEL
        and morale_state_for(target) == OpponentMoraleState.BREAK
    ):
        target.status = OpponentStatus.FLED
        target.save(update_fields=["status"])

    return outcome
