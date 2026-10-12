"""Combo outcome processing, boss phase transitions, and social combat verbs."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import F

from world.checks.social_target import SocialDifficulty, social_target_difficulty
from world.checks.types import ModifierContribution
from world.combat import services as _svc
from world.combat.constants import (
    BOSS_PARLEY_RESISTANCE_STEP,
    DEFENSE_CRITICAL_MULTIPLIER,
    DEFENSE_FULL_MULTIPLIER,
    DEFENSE_NO_DAMAGE_THRESHOLD,
    DEFENSE_REDUCED_MULTIPLIER,
    DEFENSE_REDUCED_THRESHOLD,
    ENRAGE_NARRATION,
    ENTITY_TYPE_PC,
    PHASE_SHIFT_NARRATION,
    CombatAllegiance,
    OpponentStatus,
    OpponentTier,
)
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ComboLearning,
)
from world.combat.services.combos import _broadcast_combo_finisher_narration, _group_combo_outcomes
from world.combat.services.declare_action import _dual_dispatch_combat_narration
from world.combat.services.foundations import _resolve_primary_target_sheet, accumulate_threat
from world.combat.services.opponents import minimum_break_bar_threshold
from world.combat.types import ActionOutcome
from world.conditions.constants import Allegiance
from world.fatigue.constants import EffortLevel

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import ModifierBreakdown, PendingResolution
    from world.scenes.models import Interaction


def _process_combo_outcomes(
    action_outcomes: list[ActionOutcome],
    encounter: CombatEncounter,
    round_number: int,  # reserved for future round-scoped narration
) -> list[ActionOutcome]:
    """Post-resolution pass: group combo outcomes, fire narration + discovery.

    Called from ``resolve_round`` after ``_resolve_actions`` returns and
    before ``assess_break_bar``. For each distinct combo that fired:

    1. Broadcast a joint finisher narration naming all contributors (if ≥2).
    2. Fire the discovery ceremony for first-ever triggers.
    3. Increment each contributor's ``ComboLearning.use_count``.
    4. Check for signature flourish unlock.

    Single-contributor combos keep the existing per-PC narration (backward
    compatible — the per-PC ``_record_and_broadcast_pc_action`` already ran).
    """

    # Group outcomes by combo_used.
    combo_groups = _group_combo_outcomes(action_outcomes)

    for group in combo_groups.values():
        combo = group[0][0].combo_used
        # _group_combo_outcomes only ever groups outcomes with combo_used set.
        assert combo is not None  # noqa: S101  # type narrowing for ty
        participant_sheets = [p.character_sheet for _, p in group]

        # 1. Joint finisher narration (only for multi-contributor combos).
        _MULTI_CONTRIBUTOR_THRESHOLD = 2
        if len(group) >= _MULTI_CONTRIBUTOR_THRESHOLD:
            _broadcast_combo_finisher_narration(combo, group, round_number, encounter)

        # 2. Fire discovery ceremony for first-ever triggers.
        was_known = ComboLearning.objects.filter(
            combo=combo,
            character_sheet__in=participant_sheets,
        ).exists()
        if not was_known and combo.discoverable_via_combat:
            from world.combat.combo_discovery import fire_combo_discovery  # noqa: PLC0415

            fire_combo_discovery(
                combo=combo,
                participant_sheets=participant_sheets,
                scene=encounter.scene,
            )

        # 3. Increment use_count for each contributor.
        for sheet in participant_sheets:
            ComboLearning.objects.filter(
                combo=combo,
                character_sheet=sheet,
            ).update_with_reason(
                reason="issue #3817: intentional atomic write",
                use_count=F("use_count") + 1,
            )

    return action_outcomes


# ---------------------------------------------------------------------------
# Defensive check integration
# ---------------------------------------------------------------------------


def _damage_multiplier_for_success(success_level: int) -> float:
    """Map a check success_level to a damage multiplier.

    Args:
        success_level: The ``CheckResult.success_level`` value.

    Returns:
        Float multiplier applied to NPC base damage.
    """
    if success_level >= DEFENSE_NO_DAMAGE_THRESHOLD:
        return 0.0
    if success_level >= DEFENSE_REDUCED_THRESHOLD:
        return DEFENSE_REDUCED_MULTIPLIER
    if success_level <= -1:
        return DEFENSE_CRITICAL_MULTIPLIER
    return DEFENSE_FULL_MULTIPLIER


# ---------------------------------------------------------------------------
# Boss phase transitions
# ---------------------------------------------------------------------------


def check_and_advance_boss_phase(
    opponent: CombatOpponent,
) -> BossPhase | None:
    """Check whether a boss should advance to the next phase and apply it.

    Transition happens when the boss's health drops to or below a phase's
    ``health_trigger_percentage``. The next phase (by ``phase_number``) whose
    trigger is satisfied and whose ``phase_number`` is greater than the
    opponent's ``current_phase`` is activated.

    On transition:
    - ``opponent.current_phase`` advances.
    - ``threat_pool``, ``soak_value`` are swapped from the new phase.
    - ``probing_current`` is reset to zero.
    - If the new phase has a ``probing_threshold``, it overwrites the
      opponent's ``probing_threshold``.
    - A dramatic surge fires for every ACTIVE PC (#3445): BOSS_ENRAGE when the
      phase raises damage_multiplier, else BOSS_PHASE.
    - The room is told (#3552): the phase's authored ``description`` when set,
      else a generic shift line; an enraging transition adds an enrage line.
      Not curve-gated, unlike the surge.

    Args:
        opponent: The boss opponent to check.

    Returns:
        The ``BossPhase`` that was activated, or ``None`` if no transition.
    """
    phases = list(
        BossPhase.objects.filter(
            opponent=opponent,
            phase_number__gt=opponent.current_phase,
        ).order_by("phase_number")
    )

    health_pct = opponent.health_percentage
    previous_multiplier = opponent.damage_multiplier

    for phase in phases:
        if phase.health_trigger_percentage is None:
            continue
        if health_pct <= phase.health_trigger_percentage:
            _apply_phase_transition(opponent, phase)
            _spawn_reinforcements(opponent.encounter, phase)
            _surge_on_phase_transition(opponent, phase, previous_multiplier)
            _narrate_phase_transition(
                opponent, phase, enraged=phase.damage_multiplier > previous_multiplier
            )
            return phase

    return None


def _surge_on_phase_transition(
    opponent: CombatOpponent,
    phase: BossPhase,
    previous_multiplier: Decimal,
) -> None:
    """Fire the boss-beat surge for a transition that just landed (#3445).

    The beat is BOSS_ENRAGE when the new phase makes the boss hit harder and
    BOSS_PHASE otherwise - mutually exclusive, so one transition is one surge.
    A phase that only grants ``extra_actions`` is a plain phase beat, per the
    issue's ratified decision 1.
    """
    from world.combat.escalation import apply_boss_phase_surge  # noqa: PLC0415

    apply_boss_phase_surge(
        opponent=opponent,
        enraged=phase.damage_multiplier > previous_multiplier,
    )


def _narrate_phase_transition(
    opponent: CombatOpponent,
    phase: BossPhase,
    *,
    enraged: bool,
) -> None:
    """Tell the room a boss just changed phase (#3552).

    The dramatic surge for the same transition is generic (ADR-0098 never names
    the subject) and curve-gated, so until now a phase change was invisible at
    the table. ``BossPhase.description`` is authored per phase for exactly this
    moment (copied from ``CreaturePhaseTemplate`` at spawn) and had no reader.
    Dual-dispatched so telnet sees the same line.
    """
    line = phase.description.strip() or PHASE_SHIFT_NARRATION.format(name=opponent.name)
    _dual_dispatch_combat_narration(opponent.encounter, line)
    if enraged:
        _dual_dispatch_combat_narration(
            opponent.encounter, ENRAGE_NARRATION.format(name=opponent.name)
        )


def _apply_phase_transition(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Stamp all phase-sourced fields onto the opponent and save."""
    opponent.current_phase = phase.phase_number
    if phase.threat_pool_id:
        opponent.threat_pool = phase.threat_pool
    opponent.soak_value = phase.soak_value
    opponent.probing_current = 0
    if phase.probing_threshold is not None:
        opponent.probing_threshold = phase.probing_threshold
    _stamp_enrage(opponent, phase)
    _stamp_break_bar(opponent, phase)
    opponent.save(
        update_fields=[
            "current_phase",
            "threat_pool_id",
            "soak_value",
            "probing_current",
            "probing_threshold",
            "damage_multiplier",
            "actions_per_round",
            "break_bar_threshold",
            "break_bar_current",
            "vulnerability_rounds",
            "vulnerability_intensity_bonus",
            "vulnerability_rounds_remaining",
        ],
    )


def _stamp_enrage(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Stamp damage multiplier and actions_per_round from phase config."""
    opponent.damage_multiplier = phase.damage_multiplier
    if phase.actions_per_round is not None:
        opponent.actions_per_round = phase.actions_per_round + phase.extra_actions
    else:
        opponent.actions_per_round = opponent.actions_per_round + phase.extra_actions


def _stamp_break_bar(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Reset the break bar from the new phase's break-bar config.

    Re-applies the pacing floor (#2642) on top of the phase's authored
    threshold — ``_stamp_phase_break_bar_config`` already clamps it at clone
    time, but this keeps the invariant self-evident at the site that actually
    writes the opponent's live ``break_bar_threshold`` on a phase transition.
    """
    if phase.break_bar_threshold > 0:
        threshold = max(phase.break_bar_threshold, minimum_break_bar_threshold())
        opponent.break_bar_threshold = threshold
        opponent.break_bar_current = threshold
        opponent.vulnerability_rounds = phase.vulnerability_rounds
        opponent.vulnerability_intensity_bonus = phase.vulnerability_intensity_bonus
        opponent.vulnerability_rounds_remaining = 0
    else:
        opponent.break_bar_threshold = 0
        opponent.break_bar_current = 0
        opponent.vulnerability_rounds_remaining = 0


def _spawn_reinforcements(encounter: CombatEncounter, phase: BossPhase) -> None:
    """Spawn reinforcement adds on phase entry."""
    if phase.reinforcement_template_id is None or phase.reinforcement_count <= 0:
        return
    for _ in range(phase.reinforcement_count):
        _svc.add_opponent(
            encounter,
            name=phase.reinforcement_template.name,
            tier=phase.reinforcement_template.tier,
            threat_pool=phase.reinforcement_template.threat_pool,
            max_health=20,
            auto_phases=False,
        )


# ---------------------------------------------------------------------------
# Round resolution orchestrator
# ---------------------------------------------------------------------------


def _record_combat_consequence(  # noqa: PLR0913 - mirrors record_consequence_outcome's fields
    sheet: CharacterSheet,
    check_type: CheckType,
    pool: ConsequencePool,
    pending: PendingResolution,
    breakdown: ModifierBreakdown,
    *,
    interaction: Interaction | None,
    summary: str,
) -> None:
    """Persist ConsequenceOutcome provenance for a pool-routed combat resolution.

    Mirrors vitals' _record_combat_outcome guard: a sourceless ConsequenceOutcome
    is forbidden, so skip when no interaction anchor exists (sheet without a
    PRIMARY persona). Shared by flee and encounter-aftermath resolution.
    """
    if interaction is None:
        return

    from actions.types import WeightedConsequence  # noqa: PLC0415
    from world.checks.services import record_consequence_outcome  # noqa: PLC0415

    selected = pending.selected_consequence
    if isinstance(selected, WeightedConsequence):
        selected = selected.consequence
    record_consequence_outcome(
        sheet,
        check_type,
        pool,
        selected if selected.pk is not None else None,
        breakdown,
        combat_interaction=interaction,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Social/mental combat verb resolution (#2015)
# ---------------------------------------------------------------------------


def _social_combat_difficulty(
    target: CombatOpponent,
    *,
    actor_sheet: CharacterSheet,
    check_type: CheckType,
    effort_level: str = EffortLevel.MEDIUM,
) -> SocialDifficulty:
    """Grade a social-combat check against an opponent (#2015, #4145).

    Delegates to ``social_target_difficulty`` so combat verbs, scenes and standoffs share
    one grade: Composure defense via ``compute_resist_increment`` plus
    ``MINDLESS_MORALE_RESISTANCE`` for a mindless target (a high resistance tier, not a
    wall). Rally targets an ally and never grades here.

    ``target_level=target.level`` (whole-branch-review fix, #2707): an ephemeral
    ``CombatOpponent`` has no ``CharacterClassLevel`` rows, so without the override it
    would floor at level 1 regardless of its authored ``level``. The override SUBSTITUTES
    the authored level for the objectdb-resolved one; it does not add a second level term.
    """
    from world.combat.constants import MINDLESS_MORALE_RESISTANCE  # noqa: PLC0415
    from world.combat.morale import tier_has_morale  # noqa: PLC0415

    return social_target_difficulty(
        actor_sheet=actor_sheet,
        target_character=target.objectdb,
        check_type=check_type,
        target_level=target.level,
        resist_effort=effort_level,
        mindless_resistance=0 if tier_has_morale(target) else MINDLESS_MORALE_RESISTANCE,
    )


def _social_verb_success_level(
    participant: CombatParticipant,
    check_type_name: str,
    action: CombatRoundAction,
    target: CombatOpponent,
) -> int:
    """Look up a social verb's CheckType, grade it against ``target`` and roll it (#4145).

    A missing or inactive CheckType resolves as a failed roll (success level 0).
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=check_type_name, is_active=True).first()
    if check_type is None:
        return 0
    graded = _social_combat_difficulty(
        target, actor_sheet=participant.character_sheet, check_type=check_type
    )
    return _resolve_social_check(
        participant,
        check_type,
        graded.difficulty,
        target=_resolve_primary_target_sheet(action),
        extra_contributions=graded.contributions,
    )


def _resolve_social_check(
    participant: CombatParticipant,
    check_type: CheckType,
    target_difficulty: int,
    target: CharacterSheet | None = None,
    extra_contributions: list[ModifierContribution] | None = None,
) -> int:
    """Roll a social-combat check and return the success_level (#2015).

    Routes modifiers through ``collect_check_modifiers`` (the same seam combat uses),
    folding in ``extra_contributions`` (the actor-side terms from
    ``social_target_difficulty``), then ``perform_check``. Returns
    ``check_result.success_level``.

    ``target`` (#2536 Task 6 fold-in fix, extended to Parley on review): the
    acting participant's declared opponent, when this social action has one
    — threaded into ``SituationContext.target`` so target-keyed CHECK_BONUS
    perks (``TARGET_DISTRACTED``/``TARGET_SWAYED_BY_ALLY``/
    ``TARGET_FOCUSED_ELSEWHERE``/``TARGET_FAVORABLY_DISPOSED``) can fire on
    Demoralize/Taunt/Parley, whose callers all resolve
    ``_resolve_primary_target_sheet(action)`` and pass it through. Rally
    (targets an ally, not an opponent) keeps the default ``None`` — it has no
    opposing target for a TARGET_* situation to key off.
    """
    from world.checks.services import collect_check_modifiers, perform_check  # noqa: PLC0415
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    character = participant.character_sheet.character
    breakdown = collect_check_modifiers(
        participant.character_sheet,
        check_type,
        scene=participant.encounter.scene,
        extra_contributions=extra_contributions,
    )
    # #2536 Task 5 review fix (Task 6: now target-threaded for callers that
    # have one — see the docstring above): thread the live round context so
    # CHECK_BONUS situational perks can fire on Rally/Demoralize/Taunt/Parley.
    situation_ctx = SituationContext(
        holder=participant.character_sheet,
        subject=participant.character_sheet,
        target=target,
        resolution=CombatRoundContext(participant),
    )
    result = perform_check(
        character,
        check_type,
        target_difficulty=target_difficulty,
        extra_modifiers=breakdown.total,
        situation_ctx=situation_ctx,
    )
    return result.success_level or 0


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


def _resolve_demoralize(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared demoralize — break an opponent's nerve (#2015).

    Rolls the Demoralize check (presence + Persuasion + Intimidation) against the
    target's Composure (+ mindless resistance). On success, depletes morale.
    """
    from world.combat.constants import DEMORALIZE_MORALE_PER_LEVEL  # noqa: PLC0415
    from world.combat.morale import apply_morale_damage, tier_has_morale  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is None:
        return outcome

    success_level = _social_verb_success_level(participant, "Demoralize", action, target)

    if success_level < 1:
        # Failed: mindless targets narrate "the construct is unmoved."
        if not tier_has_morale(target):
            outcome.summary = "The construct is unmoved."
        return outcome

    apply_morale_damage(target, success_level * DEMORALIZE_MORALE_PER_LEVEL)
    return outcome


def _resolve_taunt(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared taunt — draw an NPC's aggro (#2015).

    Rolls the Taunt check (wits + Persuasion + Intimidation) against the target's
    Composure. On success, accumulates threat on the existing ThreatRecord seam.
    """
    from world.combat.constants import TAUNT_THREAT_PER_LEVEL  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is not None:
        success_level = _social_verb_success_level(participant, "Taunt", action, target)

        if success_level >= 1:
            accumulate_threat(
                participant.encounter,
                target,
                participant,
                success_level * TAUNT_THREAT_PER_LEVEL,
            )

    return outcome


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


def _resolve_charge_movement(participant: CombatParticipant, action: CombatRoundAction) -> None:
    """Move *participant*'s character onto the CHARGE target's position (#1843).

    Called unconditionally at resolution time — reachability was already
    validated at declaration (``declare_charge``), but the round may have
    moved other combatants since; force-moving unconditionally here mirrors
    the existing Guardian blink-protect call site
    (``world.areas.positioning.services.force_move_to_position``) rather than
    re-validating and potentially fizzling a declared charge on a stale check.
    No-ops when either side is unpositioned (lenient, matches declare-time).
    """
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        position_of,
    )

    target = action.focused_opponent_target
    if target is None or target.objectdb is None:
        return
    dest = position_of(target.objectdb)
    if dest is None:
        return
    rider = participant.character_sheet.character
    if position_of(rider) is None:
        return
    force_move_to_position(rider, dest)


def _resolve_use_item(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a USE_ITEM combat maneuver by dispatching UseItemAction (#2023, #2120).

    Reuses the built UseItemAction machinery (prerequisites, effect application)
    rather than duplicating it. The item is resolved from the action's
    ``item_instance`` FK; the actor is the participant's character. Using an
    item costs the round's focused action — it is a primary maneuver, mutually
    exclusive with ``focused_action``, like FLEE/COVER/INTERPOSE.

    Two bugs fixed here (#2120): (1) the declared target was never forwarded,
    so any on-use item with a non-null ``on_use_target_kind`` (e.g. a healing
    potion used on an ally) silently self-targeted — ``focused_ally_target``/
    ``focused_opponent_target`` are now threaded through as ``target``. (2)
    ``UseItemAction`` expects an ``ObjectDB`` for its ``item`` kwarg
    (``resolve_item_instance`` walks ``target.item_instance``), but this used
    to pass the ``ItemInstance`` row itself — now resolved to its
    ``game_object`` first.
    """
    from actions.definitions.items import UseItemAction  # noqa: PLC0415

    outcome = ActionOutcome(
        entity_type=ENTITY_TYPE_PC,
        entity_label=str(participant),
    )
    outcome.participant_id = participant.pk

    if action.item_instance is not None:
        item_object = action.item_instance.game_object
        if item_object is not None:
            character = participant.character_sheet.character
            target: ObjectDB | None = None
            if action.focused_ally_target is not None:
                target = action.focused_ally_target.character_sheet.character
            elif action.focused_opponent_target is not None:
                target = action.focused_opponent_target.objectdb

            UseItemAction().run(actor=character, item=item_object, target=target)
            # UseItemAction's effects (healing, conditions) are applied by the action
            # itself; the combat round just needs to know the maneuver resolved.

    return outcome
