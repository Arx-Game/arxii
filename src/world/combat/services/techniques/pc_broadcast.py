"""Recording and broadcasting a PC action."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.techniques.cast_audience import _resolve_combat_cast_audience
from world.combat.types import ActionOutcome, CombatTechniqueResult, OpponentDamageResult

if TYPE_CHECKING:
    from world.magic.models import Technique


def _opponent_labels(outcome: ActionOutcome) -> dict[int, str] | None:
    """Opponent id to player-facing name for an outcome that hurt several opponents (#4842).

    An area cast names each opponent with its own damage. One query for the names
    (``CombatOpponent.name``, what ``target.name`` is), and none when the outcome touched
    fewer than two opponents.
    """
    opponent_ids = {
        dr.opponent_id
        for dr in outcome.damage_results
        if isinstance(dr, OpponentDamageResult) and dr.opponent_id is not None
    }
    if len(opponent_ids) < 2:  # noqa: PLR2004 - one opponent is the single-target line
        return None
    return dict(CombatOpponent.objects.filter(pk__in=opponent_ids).values_list("pk", "name"))


def _record_and_broadcast_pc_action(  # noqa: PLR0913
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique,
    target: CombatOpponent | None,
    outcome: ActionOutcome,
    combat_result: CombatTechniqueResult | None,
) -> None:
    """Record the ACTION-mode Interaction and broadcast the outcome narration."""
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        create_action_interaction,
        render_action_declaration_label,
        render_action_outcome_narration,
        render_unattributed_action_narration,
        target_persona_for_round_action,
    )
    from world.scenes.interaction_services import push_interaction  # noqa: PLC0415

    audience = _resolve_combat_cast_audience(participant, technique)

    # #3787 Task 5 - who this action was about. focused_ally_target's persona
    # when the declared target was an ally; None for an NPC opponent target (no
    # Persona behind an NPC - correct, not a gap) or no target at all.
    target_persona = target_persona_for_round_action(action)
    target_personas = [target_persona] if target_persona is not None else None

    # Only the attack path returns a CombatTechniqueResult (which carries fury);
    # the non-attack path returns a CombatTechniqueResolution with no fury field.
    fury_committed = (
        combat_result.fury_committed if isinstance(combat_result, CombatTechniqueResult) else None
    )
    interaction = create_action_interaction(
        participant=participant,
        round_number=action.round_number,
        summary_label=render_action_declaration_label(action, ally_persona=target_persona),
        strain_committed=(
            combat_result.declared_strain_commitment
            if isinstance(combat_result, CombatTechniqueResult)
            else 0
        ),
        strain_effective=(
            combat_result.effective_strain_commitment
            if isinstance(combat_result, CombatTechniqueResult)
            else 0
        ),
        strain_power_bonus=(
            combat_result.strain_power_bonus
            if isinstance(combat_result, CombatTechniqueResult)
            else 0
        ),
        fury_committed=fury_committed,
        target_personas=target_personas,
    )
    if interaction is not None:
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        if audience.concealed:
            # Before push_interaction, which reads .visibility to decide whether to
            # broadcast room-wide. Concealing after the push would leak the technique
            # name live and hide it only on scene-log re-read.
            from world.magic.services.cast_observation import (  # noqa: PLC0415
                conceal_action_interaction,
            )

            conceal_action_interaction(interaction, audience)
        push_interaction(interaction)
        if combat_result is not None:
            from world.scenes.power_ledger_services import persist_power_ledger  # noqa: PLC0415

            persist_power_ledger(interaction=interaction, ledger=combat_result.power_ledger)

    from world.magic.services.signature_effects import resolve_signature_snippet  # noqa: PLC0415
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        paid_price_snippet,
        technique_display_name,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    target_label = target.name if target is not None else None
    caster_character = participant.character_sheet.character
    signature_snippet = resolve_signature_snippet(caster_character, technique)
    # #4099: the price THIS resolved cast paid (use_technique's one decision, made at
    # resolution, not declaration), never the hold's price.
    price_snippet = paid_price_snippet(
        combat_result.technique_use_result.price_paid
        if isinstance(combat_result, CombatTechniqueResult)
        else None
    )
    interaction_result = next(
        (dr.damage_interaction for dr in outcome.damage_results if dr.damage_interaction),
        None,
    )
    opponent_labels = _opponent_labels(outcome)
    target_opponent_id = target.pk if target is not None else None
    narration = render_action_outcome_narration(
        # The persona this PC is CURRENTLY presenting as, not str(participant)
        # -> "Sheet for {key}" (#4091 fix round 2). One call per action.
        actor_label=active_persona_for_sheet(participant.character_sheet).name,
        technique_name=technique_display_name(caster_character, technique),
        target_label=target_label,
        outcome=outcome,
        power_ledger=combat_result.power_ledger if combat_result is not None else None,
        signature_snippet=signature_snippet,
        price_snippet=price_snippet,
        interaction_result=interaction_result,
        hit_text=technique.hit_narration,
        miss_text=technique.miss_narration,
        target_opponent_id=target_opponent_id,
        opponent_labels=opponent_labels,
    )
    # Rendered unconditionally rather than under `if audience.concealed`: it is a pure
    # string build over data already in hand, and branching here would put the
    # concealment decision in two places.
    unattributed_narration = render_unattributed_action_narration(
        target_label=target_label,
        outcome=outcome,
        target_opponent_id=target_opponent_id,
        opponent_labels=opponent_labels,
    )
    broadcast_action_outcome(
        encounter=participant.encounter,
        narration=narration,
        audience=audience,
        unattributed_narration=unattributed_narration,
        target_personas=target_personas,
    )
