"""Resolving a PC's combat action."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from actions.errors import ActionDispatchError
from world.combat import services as _svc
from world.combat.constants import (
    ENTITY_TYPE_PC,
    ActionCategory,
    CombatAllegiance,
    CombatManeuver,
    EncounterType,
    OpponentStatus,
)
from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.services.combos.combo_outcome import _apply_combo_rider
from world.combat.services.declarations.charge import _resolve_charge_movement
from world.combat.services.npc.windup import _apply_windup_interception_rider
from world.combat.services.rounds.maneuvers import _STANDALONE_MANEUVER_RESOLVERS
from world.combat.services.techniques.allegiance_break import _attempt_allegiance_breaks_for_action
from world.combat.services.techniques.entrance_moment import _maybe_suggest_entrance_dramatic_moment
from world.combat.services.techniques.insight import _maybe_produce_insight_for_cast
from world.combat.services.techniques.npc_regard import _maybe_record_npc_regard_on_defeat
from world.combat.services.techniques.pc_broadcast import _record_and_broadcast_pc_action
from world.combat.services.techniques.spectacle import _maybe_apply_spectacle_for_action
from world.combat.services.techniques.technique_targets import finds_no_one_in_reach
from world.combat.services.techniques.weakness_selection import (
    _maybe_create_weakness_selection_for_cast,
)
from world.combat.types import ActionOutcome, CombatTechniqueResult
from world.fatigue.services import apply_fatigue

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.checks.types import CheckResult
    from world.magic.models import Technique

    PerformCheckFn = Callable[..., CheckResult]


def _run_combat_technique_pipeline(
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique,
    fatigue_category: str,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Run the magic combat-technique pipeline for a single focused action.

    Resolves the cast check (check type plus the technique skill term) and rolls it via
    ``resolve_combat_technique``. Raises ``ActionDispatchError(TECHNIQUE_NOT_COMBAT_READY)``
    if the technique has no action_template (not configured for combat use).
    """
    template = technique.action_template
    if template is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415

    cast_check = resolve_cast_check(participant.character_sheet.character, technique)
    if cast_check is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    return _svc.resolve_combat_technique(
        participant=participant,
        action=action,
        fatigue_category=fatigue_category,
        cast_check=cast_check,
        offense_check_fn=offense_check_fn,
    )


def _broadcast_fizzle_no_one_in_reach(
    participant: CombatParticipant, action: CombatRoundAction
) -> None:
    """Narrate a strike whose target left reach before the PC's slot (costs nothing).

    A concealed caster stays concealed: the line goes through the cast's own audience,
    and a strike that touched no one leaves nothing for the lower tiers to perceive.
    """
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        target_persona_for_round_action,
    )
    from world.combat.services.techniques.cast_audience import (  # noqa: PLC0415
        _resolve_combat_cast_audience,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    target_persona = target_persona_for_round_action(action)
    broadcast_action_outcome(
        encounter=participant.encounter,
        narration=f"{active_persona_for_sheet(participant.character_sheet).name}'s strike "
        "finds no one in reach.",
        audience=_resolve_combat_cast_audience(participant, action.focused_action),
        unattributed_narration="",
        target_personas=[target_persona] if target_persona is not None else None,
    )


def _broadcast_cast_stopped(
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique,
    combat_result: CombatTechniqueResult,
) -> None:
    """Narrate a cast stopped before it went off, never as a miss (#4801).

    The Soulfray gate (a stage taken after the declaration, risk not accepted) or a
    pre-cast trigger stopped it: nothing was spent or rolled. The room hears that it
    faltered; the caster is told why.
    """
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        target_persona_for_round_action,
    )
    from world.combat.services.techniques.cast_audience import (  # noqa: PLC0415
        _resolve_combat_cast_audience,
    )
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        technique_display_name,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    character = participant.character_sheet.character
    actor = active_persona_for_sheet(participant.character_sheet).name
    target_persona = target_persona_for_round_action(action)
    broadcast_action_outcome(
        encounter=participant.encounter,
        narration=(
            f"{actor}’s {technique_display_name(character, technique)} falters "
            "before it can be cast."
        ),
        audience=_resolve_combat_cast_audience(participant, technique),
        unattributed_narration="",
        target_personas=[target_persona] if target_persona is not None else None,
    )
    if action.declared_by_compulsion:
        reason = "Your compulsion's strike faltered at the edge of Soulfray."
    elif combat_result.technique_use_result.soulfray_warning is not None:
        reason = (
            "Your Soulfray worsened before your turn and stopped the cast. "
            "Accept the Soulfray risk when you declare to cast through it."
        )
    else:
        reason = "Something here stopped your cast before it left your hands."
    transaction.on_commit(lambda: character.msg(reason))


def _resolve_pc_action(
    participant: CombatParticipant,
    action: CombatRoundAction,
    offense_check_fn: PerformCheckFn | None = None,
) -> ActionOutcome:
    """Resolve a single PC's focused action during round resolution.

    For non-combo actions, derives the offense_check_type from the declared
    technique's action_template. The check result's success_level scales damage:
    - success_level >= 2: full base_power
    - success_level == 1: half base_power
    - success_level <= 0: zero (miss)

    Raises ActionDispatchError(TECHNIQUE_NOT_COMBAT_READY) if the technique has
    no action_template (i.e. it has not been configured for combat use).

    Fatigue is applied after the action resolves (both combo and non-combo).
    """
    standalone_resolver = _STANDALONE_MANEUVER_RESOLVERS.get(action.maneuver)
    if standalone_resolver is not None:
        return standalone_resolver(participant, action)

    # CHARGE (#1843): closes distance to the declared opponent, THEN falls
    # through to the normal weapon-attack pipeline below (no early return) —
    # CHARGE augments a normal attack via CombatTechniqueResolver's
    # CHARGE_CHECK_BONUS/CHARGE_DAMAGE_BONUS injection, it doesn't replace it.
    if action.maneuver == CombatManeuver.CHARGE:
        _resolve_charge_movement(participant, action)

    # YIELD ends a duel immediately: the yielding PC loses. Passives-only outcome;
    # _resolve_duel_completion is a no-op afterwards because the encounter is now
    # COMPLETED (yield_duel routes through complete_encounter).
    # Guard: only valid in a DUEL encounter — a YIELD in any other encounter type
    # is a no-op (treated like a passives-only round, same as COVER).
    if (
        action.maneuver == CombatManeuver.YIELD
        and participant.encounter.encounter_type == EncounterType.DUEL
    ):
        from world.combat.duels import yield_duel  # noqa: PLC0415

        yield_duel(participant)
        return ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    return resolve_pc_technique(participant, action, offense_check_fn)


def resolve_pc_technique(
    participant: CombatParticipant,
    action: CombatRoundAction,
    offense_check_fn: PerformCheckFn | None = None,
) -> ActionOutcome:
    """Resolve a PC's declared technique at its declared target (the attack half).

    ``_resolve_pc_action`` reaches it after the maneuver dispatch; a waiting strike
    (#4608) calls it directly when it fires, so defenses, ramparts, fatigue, anima and
    the log line behave exactly as for any attack. Reach is re-checked live first: a
    target out of reach fizzles for free.
    """
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    outcome.participant_id = participant.pk

    technique = action.focused_action
    if technique is None:
        # Passives-only round (e.g. flee) — no focused action to resolve.
        return outcome

    outcome.effect_type_id = technique.effect_type_id

    # #4607: positions moved since the declaration (NPCs step in their own slots), so
    # reach is re-checked live, after any CHARGE movement and before the pipeline,
    # fatigue or anima. The player chose the target, so the action does not retarget.
    if finds_no_one_in_reach(participant, action, technique):
        _broadcast_fizzle_no_one_in_reach(participant, action)
        return outcome

    target = action.focused_opponent_target
    fatigue_category = action.focused_category or ActionCategory.PHYSICAL

    # combat_result is only set on magic-pipeline paths; the combo rider
    # path produces no CombatTechniqueResult.
    combat_result: CombatTechniqueResult | None = None

    # Combo-upgraded actions still run the magic pipeline (the contributor's
    # own technique resolves normally), AND get the combo rider appended.
    # Non-combo actions run the pipeline as before. The only case where the
    # pipeline is skipped: combo-upgraded with no target (defeated opponent).
    # A combo upgrade must not suppress an ally-targeted technique.  Support
    # effects (heals, wards, and buffs) resolve through their normal geometry;
    # only an opponent target can receive the combo's damage rider.
    run_pipeline = (
        not action.combo_upgrade or target is not None or action.focused_ally_target is not None
    )
    # #4147: health before the blow, so a devastating action can be judged afterwards.
    health_before = dict(
        participant.encounter.opponents.filter(
            status=OpponentStatus.ACTIVE, allegiance=CombatAllegiance.ENEMY
        ).values_list("pk", "health")
    )
    if run_pipeline:
        combat_result = _svc._run_combat_technique_pipeline(  # noqa: SLF001 (test patch seam)
            participant, action, technique, fatigue_category, offense_check_fn
        )
        # The non-attack path returns a CombatTechniqueResolution, which carries no use result.
        if (
            isinstance(combat_result, CombatTechniqueResult)
            and not combat_result.technique_use_result.confirmed
        ):
            # Stopped before it went off: like a fizzle, it costs nothing (#4801).
            _broadcast_cast_stopped(participant, action, technique, combat_result)
            return outcome
        outcome.damage_results.extend(combat_result.damage_results)
        if action.from_entrance:
            _maybe_suggest_entrance_dramatic_moment(participant, combat_result)
        _maybe_produce_insight_for_cast(participant, combat_result, technique)
        _maybe_create_weakness_selection_for_cast(participant, combat_result, technique, target)

    # Combo rider: appended in addition to the pipeline result when the
    # action is combo-upgraded and the target is alive.
    if action.combo_upgrade and target is not None:
        _apply_combo_rider(participant, action, target, outcome)

    # #4091 Decision 16: one break-attempt roll per opponent this action
    # harmed, against the combined pipeline + combo-rider damage. Must run
    # after both of the above and before the wind-up rider below (which is
    # not part of this blow's own pressure).
    _attempt_allegiance_breaks_for_action(participant, outcome)

    # Wind-up interception rider (#2637 design 4): a landing hit on a
    # winding-up opponent downgrades its telegraphed attack. No new button —
    # rides the existing damage-landed moment.
    if target is not None:
        _apply_windup_interception_rider(target, outcome, participant)

    # Apply fatigue after action resolves
    apply_fatigue(
        participant.character_sheet,
        fatigue_category,
        technique.anima_cost,
        action.effort_level,
    )

    _record_and_broadcast_pc_action(
        participant=participant,
        action=action,
        technique=technique,
        target=target,
        outcome=outcome,
        combat_result=combat_result,
    )

    # Earned displays shake the enemy witnesses (#4147); the credit line follows the
    # action's own outcome line.
    _maybe_apply_spectacle_for_action(participant, technique, combat_result, outcome, health_before)

    # Nemesis/toxic-NPC-bond regard hook (#2039): a PC defeating a notable
    # (persona-backed) NPC opponent records a PC_FOILED_NPC_PLAN regard event.
    # A mook/persona-less opponent's defeat is deliberately a no-op — no
    # NpcRegard row is ever created for it.
    _maybe_record_npc_regard_on_defeat(participant, action, target, outcome)

    return outcome
