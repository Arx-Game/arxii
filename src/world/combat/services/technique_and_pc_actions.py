"""Combat technique resolution, PC action pipeline, and ordered action resolution."""

from __future__ import annotations

from collections.abc import Callable
import contextlib
from typing import TYPE_CHECKING

from actions.errors import ActionDispatchError
from world.combat import services as _svc
from world.combat.constants import (
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    JOUST_DECISIVE_MARGIN,
    ActionCategory,
    CombatAllegiance,
    CombatManeuver,
    EncounterType,
    OpponentStatus,
    SpectacleKind,
)
from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.boss_and_social import (
    _resolve_charge_movement,
    _resolve_demoralize,
    _resolve_parley,
    _resolve_rally,
    _resolve_taunt,
    _resolve_use_item,
)
from world.combat.services.damage_and_landing import _apply_combo_rider
from world.combat.services.foundations import (
    _build_affected_targets,
    _check_combat_target_prerequisites,
    _resolve_primary_target_sheet,
    _sum_active_flat_bonuses,
    _vulnerability_intensity_bonus,
)
from world.combat.services.pc_and_npc_actions import (
    _attempt_allegiance_breaks_for_action,
    _maybe_create_weakness_selection_for_cast,
    _maybe_produce_insight_for_cast,
    _maybe_record_npc_regard_on_defeat,
    _maybe_suggest_entrance_dramatic_moment,
    _record_and_broadcast_pc_action,
    _resolve_flee,
)
from world.combat.services.technique_resolver import CombatTechniqueResolver
from world.combat.services.weapons_and_npc_attacks import (
    _resolve_npc_action,
    effective_weapon_profile,
)
from world.combat.services.windup_and_attacks import _apply_windup_interception_rider
from world.combat.types import (
    ActionOutcome,
    CombatTechniqueResolution,
    CombatTechniqueResult,
    OpponentDamageResult,
)
from world.fatigue.services import apply_fatigue

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.magic.models import FuryTier, Technique
    from world.magic.types import TechniqueUseResult

    PerformCheckFn = Callable[..., CheckResult]


def _build_combat_result(
    technique_use_result: TechniqueUseResult,
    resolver: CombatTechniqueResolver,  # noqa: ARG001 - kept for future extensibility
    fury_committed: FuryTier | None = None,
) -> CombatTechniqueResult:
    """Translate use_technique's outcome into the adapter's return shape."""
    if not technique_use_result.confirmed:
        return CombatTechniqueResult(
            damage_results=[],
            applied_conditions=[],
            technique_use_result=technique_use_result,
            fury_committed=fury_committed,
        )

    resolution = technique_use_result.resolution_result
    # Defensive assertion against programmer error — service contract
    # is that combat resolvers return CombatTechniqueResolution.
    if not isinstance(resolution, CombatTechniqueResolution):
        msg = f"Expected CombatTechniqueResolution, got {type(resolution).__name__}"
        raise TypeError(msg)

    return CombatTechniqueResult(
        damage_results=list(resolution.damage_results),
        applied_conditions=list(resolution.applied_conditions),
        technique_use_result=technique_use_result,
        power_ledger=resolution.power_ledger,
        fury_committed=fury_committed,
        removed_conditions=list(resolution.removed_conditions),
    )


def resolve_combat_technique(
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    fatigue_category: str,
    offense_check_type: CheckType,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Route a damage-path combat technique through use_technique.

    Builds a CombatTechniqueResolver and passes it to use_technique as
    resolve_fn. The magic envelope handles anima, soulfray, mishap,
    PRE_CAST/CAST events, reactive scar interception, and corruption.
    The resolver does the offense check + damage application inside
    that envelope.

    Soulfray warning is auto-confirmed at round resolution time —
    frontend handles preview before submission.

    TECHNIQUE_AFFECTED fires per target via _build_affected_targets:
    opponent target → opp.objectdb; ally target → ally character ObjectDB.

    Other pull effect kinds are deferred:
    - INTENSITY_BUMP: needs runtime stats to accept combat context
    - CAPABILITY_GRANT: tied to non-attack pipeline
    - NARRATIVE_ONLY: cosmetic surfacing
    - VITAL_BONUS: already wired through recompute_max_health_with_threads
    """
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.fury import run_fury_for_action  # noqa: PLC0415

    encounter = participant.encounter
    pull_flat_bonus = _sum_active_flat_bonuses(participant, encounter)

    resolver = CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=pull_flat_bonus,
        fatigue_category=fatigue_category,
        offense_check_type=offense_check_type,
        offense_check_fn=offense_check_fn,
    )

    targets = _build_affected_targets(participant, action)
    _check_combat_target_prerequisites(
        action.focused_action, participant.character_sheet.character, targets
    )

    fury_res = run_fury_for_action(
        character=participant.character_sheet.character,
        fury_commitment=action.fury_commitment,
        fury_anchor=action.fury_anchor,
        source_technique=action.focused_action,
    )

    # Signature-motif bonus (#1582): a flat intensity delta on the signed technique's
    # thread folds into power derivation, exactly as in the standalone cast path
    # (no-op / 0 when unsigned).
    from world.magic.services.signature_effects import signature_intensity_delta  # noqa: PLC0415

    sig_intensity_delta = signature_intensity_delta(
        participant.character_sheet.character, action.focused_action
    )

    technique_use_result = use_technique(
        character=participant.character_sheet.character,
        technique=action.focused_action,
        resolve_fn=resolver,
        confirm_soulfray_risk=action.confirm_soulfray_risk,
        strain_commitment=action.strain_commitment,
        targets=targets,
        lethal=encounter.is_lethal,
        control_penalty=fury_res.control_penalty if fury_res else 0,
        power_intensity_bonus=(
            (fury_res.intensity_bonus if fury_res else 0)
            + sig_intensity_delta
            + _vulnerability_intensity_bonus(action)
        ),
        # #2536 Task 4: thread the live round context so situational-perk
        # POWER_BONUS providers can read combat-positioning situations
        # (AT_RANGE/IN_MELEE/SURROUNDED/...). Cheap to build — CombatRoundContext
        # just wraps the already-resolved participant (its encounter rides the
        # SharedMemoryModel identity map), no extra query.
        situation_ctx=CombatRoundContext(participant),
        # #2536 Task 4 review fix: thread the cast's primary target's
        # CharacterSheet so target-keyed situational-perk POWER_BONUS
        # providers (TARGET_DISTRACTED/TARGET_SWAYED_BY_ALLY/
        # TARGET_FOCUSED_ELSEWHERE/TARGET_FAVORABLY_DISPOSED) can fire.
        target_sheet=_resolve_primary_target_sheet(action),
    )

    return _build_combat_result(
        technique_use_result, resolver, fury_committed=fury_res.realized_tier if fury_res else None
    )


def _joust_offense_check(participant: CombatParticipant, action: CombatRoundAction) -> CheckResult:
    """Roll one side's JOUST offense check via the shared CombatTechniqueResolver seam.

    Reuses ``CombatTechniqueResolver._roll_check`` so EFFORT/PULL/bond bonuses
    and the LANCE_UNMOUNTED_PENALTY gate all compose exactly as they would for
    a normal attack (both jousters are validated Mounted+LANCE at declare
    time, so the unmounted-lance penalty never actually fires here).
    """
    from world.magic.services.anima import resolve_cast_check_type  # noqa: PLC0415

    technique = action.focused_action
    template = technique.action_template
    if template is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    offense_check_type = resolve_cast_check_type(participant.character_sheet.character, template)
    resolver = CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=0,
        fatigue_category=action.focused_category or ActionCategory.PHYSICAL,
        offense_check_type=offense_check_type,
        offense_check_fn=None,
    )
    return resolver._roll_check()  # noqa: SLF001 - same-module reuse of the shared roll seam


def _resolve_joust_pass(
    participant: CombatParticipant,
    action: CombatRoundAction,
    other: CombatParticipant,
    other_action: CombatRoundAction,
) -> None:
    """Resolve a JOUST's single opposed pass — grades by the success_level gap (#1843).

    decisive gap (>= JOUST_DECISIVE_MARGIN): loser takes the winner's lance
    weapon damage x2 + the Unhorsed condition, which force-dismounts them.
    narrow gap (>= JOUST_NARROW_MARGIN, < decisive): loser takes the winner's
    lance weapon damage x1, keeps the saddle. Tie (gap 0): both jarred, no
    damage. Damage is applied to the loser's mirror CombatOpponent via
    ``apply_damage_to_opponent`` — the same non-bypassing pipeline every
    normal duel attack already uses (defenses/soak/non-lethal PvP capping,
    ADR-0023, all fire unchanged).
    """
    from world.companions.mount_content import UNHORSED_CONDITION_NAME  # noqa: PLC0415
    from world.companions.services import MountError, dismount_companion  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    check_a = _joust_offense_check(participant, action)
    check_b = _joust_offense_check(other, other_action)
    gap = check_a.success_level - check_b.success_level

    if gap == 0:
        return  # tie — both jarred, no damage

    winner, loser = (participant, other) if gap > 0 else (other, participant)
    margin = abs(gap)

    weapon = effective_weapon_profile(winner.character_sheet.character)
    base_damage = weapon.damage if weapon is not None else 0

    loser_mirror = CombatOpponent.objects.filter(
        encounter=participant.encounter, mirrors_participant=loser
    ).first()
    if loser_mirror is None:
        return

    if margin >= JOUST_DECISIVE_MARGIN:
        _svc.apply_damage_to_opponent(
            loser_mirror,
            base_damage * 2,
            damage_type=weapon.damage_type if weapon is not None else None,
            source_sheet=winner.character_sheet,
        )
        unhorsed = ConditionTemplate.get_by_name(UNHORSED_CONDITION_NAME)
        apply_condition(
            loser.character_sheet.character,
            unhorsed,
            source_character=winner.character_sheet.character,
        )
        with contextlib.suppress(MountError):
            # Not actually mounted somehow — nothing to dismount.
            dismount_companion(loser.character_sheet)
    else:
        _svc.apply_damage_to_opponent(
            loser_mirror,
            base_damage,
            damage_type=weapon.damage_type if weapon is not None else None,
            source_sheet=winner.character_sheet,
        )


def _resolve_joust(participant: CombatParticipant, action: CombatRoundAction) -> ActionOutcome:
    """Dispatch a declared JOUST maneuver — resolves once both duelists have declared it.

    Deterministic single-resolution: only the lower-pk participant's call
    actually runs ``_resolve_joust_pass`` (avoids a schema field just to
    memoize "already resolved this round" — the higher-pk participant's own
    ``_resolve_pc_action`` pass is a no-op once its partner's pass already
    applied both sides' outcomes).
    """
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    outcome.participant_id = participant.pk

    other = (
        CombatParticipant.objects.filter(encounter=participant.encounter)
        .exclude(pk=participant.pk)
        .select_related("character_sheet")
        .first()
    )
    if other is not None:
        other_action = CombatRoundAction.objects.filter(
            participant=other, round_number=action.round_number
        ).first()
        if (
            other_action is not None
            and other_action.maneuver == CombatManeuver.JOUST
            and participant.pk <= other.pk
        ):
            _resolve_joust_pass(participant, action, other, other_action)

    return outcome


def _maybe_apply_spectacle_for_action(
    participant: CombatParticipant,
    technique: Technique,
    combat_result: CombatTechniqueResult | None,
    outcome: ActionOutcome,
    health_before: dict[int, int],
) -> None:
    """Earned displays shake the witnesses (#4147).

    Deliberately unguarded: a failure here is a bug and should fail loudly.
    """
    from world.combat.models import SpectacleConfig  # noqa: PLC0415
    from world.combat.spectacle import (  # noqa: PLC0415
        apply_spectacle,
        classify_cast,
        deliver_spectacle,
        is_devastating,
    )

    config = SpectacleConfig.load()
    kind = None
    success_level = 0
    cast_technique = None
    if isinstance(combat_result, CombatTechniqueResult):
        use = combat_result.technique_use_result
        check = use.resolution_result.check_result if use.resolution_result else None
        success_level = check.success_level if check is not None else 0
        if success_level >= 1:
            kind = classify_cast(
                technique=technique,
                runtime_intensity=use.runtime_intensity,
                success_level=success_level,
                config=config,
            )
            cast_technique = technique
    if kind is None:
        damage = _opponent_damage_totals(outcome)
        if is_devastating(damage_by_opponent=damage, health_before=health_before, config=config):
            kind = SpectacleKind.DEVASTATING_ACTION
    if kind is None:
        return
    result = apply_spectacle(
        encounter=participant.encounter,
        caster_sheet=participant.character_sheet,
        kind=kind,
        display_name=technique.name,
        success_level=success_level,
        technique=cast_technique,
    )
    deliver_spectacle(participant.encounter, result)


def _run_combat_technique_pipeline(
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique,
    fatigue_category: str,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Run the magic combat-technique pipeline for a single focused action.

    Derives the ``offense_check_type`` from the technique's action_template
    and resolves it via ``resolve_combat_technique``. Raises
    ``ActionDispatchError(TECHNIQUE_NOT_COMBAT_READY)`` if the technique has
    no action_template (not configured for combat use).
    """
    template = technique.action_template
    if template is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    from world.magic.services.anima import resolve_cast_check_type  # noqa: PLC0415

    return _svc.resolve_combat_technique(
        participant=participant,
        action=action,
        fatigue_category=fatigue_category,
        offense_check_type=resolve_cast_check_type(participant.character_sheet.character, template),
        offense_check_fn=offense_check_fn,
    )


#: Maneuvers that resolve wholly on their own, short-circuiting the technique
#: pipeline in :func:`_resolve_pc_action`. COVER is deliberately absent — it
#: falls through to the passives-only return, since its effect is the
#: ``cover_bonus`` it contributes to the sheltered ally's flee check.
_STANDALONE_MANEUVER_RESOLVERS: dict[
    str, Callable[[CombatParticipant, CombatRoundAction], ActionOutcome]
] = {
    CombatManeuver.FLEE: _resolve_flee,
    # Social/mental combat verbs (#2015): resolve as checks at round-tick.
    CombatManeuver.RALLY: _resolve_rally,
    CombatManeuver.DEMORALIZE: _resolve_demoralize,
    CombatManeuver.TAUNT: _resolve_taunt,
    CombatManeuver.PARLEY: _resolve_parley,
    # On-use items as a combat maneuver (#2023): dispatches the existing
    # UseItemAction as a primary maneuver (mutually exclusive with the focused
    # technique, like FLEE/COVER). Using an item costs the round's focused action.
    CombatManeuver.USE_ITEM: _resolve_use_item,
    # JOUST (#1843): a bilateral opposed pass between two mounted, lance-armed
    # duelists — resolved directly against the loser's mirror CombatOpponent,
    # not through the normal per-target technique pipeline (there is no single
    # "attacker vs one opponent" shape here).
    CombatManeuver.JOUST: _resolve_joust,
}


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

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    outcome.participant_id = participant.pk

    technique = action.focused_action
    if technique is None:
        # Passives-only round (e.g. flee) — no focused action to resolve.
        return outcome

    outcome.effect_type_id = technique.effect_type_id

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


def _resolve_actions(  # noqa: PLR0913 - resolution needs all check params
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
    pc_actions: dict[int, CombatRoundAction],
    npc_actions: dict[int, list[CombatOpponentAction]],
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
    offense_check_fn: PerformCheckFn | None,
    *,
    sustaining_participant_ids: frozenset[int] = frozenset(),
) -> list[ActionOutcome]:
    """Iterate resolution order and resolve each entity's action.

    ``sustaining_participant_ids`` (#2705) — participants who declared a new
    ``SustainedAction`` THIS round. Their ``CombatRoundAction`` row on the
    board is the declaration of the commitment, not an action to resolve —
    the commitment resolves later, at maturation. Precomputed by the caller
    (one query); this loop only checks membership.
    """
    outcomes: list[ActionOutcome] = []
    for entity_type, entity in resolution_order:
        if entity_type == ENTITY_TYPE_PC and isinstance(entity, CombatParticipant):
            if entity.pk in sustaining_participant_ids:
                continue
            action = pc_actions.get(entity.pk)
            if action is not None:
                outcomes.append(_resolve_pc_action(entity, action, offense_check_fn))
        elif entity_type == ENTITY_TYPE_NPC and isinstance(entity, CombatOpponent):
            outcomes.extend(
                _resolve_npc_action(entity, npc_action, defense_check_type, defense_check_fn)
                for npc_action in npc_actions.get(entity.pk, [])
            )
    return outcomes


def _opponent_damage_totals(outcome: ActionOutcome) -> dict[int, int]:
    """Aggregate only opponent damage, including repeated hits on the same opponent."""
    damage: dict[int, int] = {}
    for dealt in outcome.damage_results:
        if isinstance(dealt, OpponentDamageResult) and dealt.opponent_id is not None:
            damage[dealt.opponent_id] = damage.get(dealt.opponent_id, 0) + (dealt.damage_dealt)
    return damage
