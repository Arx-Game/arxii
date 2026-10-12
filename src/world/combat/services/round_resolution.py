"""resolve_round, the round orchestrator, and encounter settings."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import F, Prefetch
from django.utils import timezone

from world.combat.constants import EncounterType, OpponentStatus, PaceMode, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    EscalationCurve,
    PendingOpponentAttack,
    SustainedAction,
)
from world.combat.services.boss_and_social import _process_combo_outcomes
from world.combat.services.break_bar_and_protection import _resolve_clashes, assess_break_bar
from world.combat.services.combos import _revalidate_combo_upgrades, get_resolution_order
from world.combat.services.completion import (
    _check_encounter_completion,
    _classify_encounter_outcome,
    complete_encounter,
)
from world.combat.services.damage_and_landing import _resolve_sent_flying_markers
from world.combat.services.foundations import _UNSET
from world.combat.services.interpose_helpers import _resolve_declared_challenges
from world.combat.services.npc_round_and_damage import (
    _refresh_participant_trigger_handlers,
    _resolve_passive_actions,
    select_npc_actions,
)
from world.combat.services.pc_and_npc_actions import _check_boss_transitions, _narrate_held_back
from world.combat.services.reactive_and_upkeep import (
    _block_if_participant_mid_audere_majora_crossing,
    _ensure_reactive_challenges,
    _fire_round_start,
)
from world.combat.services.technique_and_pc_actions import _resolve_actions
from world.combat.services.windup_and_attacks import (
    _mature_pending_opponent_attacks,
    _mature_sustained_actions,
)
from world.combat.types import RoundResolutionResult
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.checks.models import CheckType
    from world.checks.types import CheckResult

    PerformCheckFn = Callable[..., CheckResult]


def maybe_resolve_on_ready(encounter: CombatEncounter) -> RoundResolutionResult | None:
    """Resolve the round early when every ACTIVE participant is ready (#2120).

    Only applies in ``PaceMode.READY`` — ``TIMED`` encounters keep resolving via
    the game-clock sweep (``check_and_resolve_timed_encounters``); ``MANUAL``
    encounters resolve only on an explicit GM/force-resolve call. Compares the
    ACTIVE participant count against this round's ``is_ready=True``
    ``CombatRoundAction`` count; when they're equal (and non-zero — an
    encounter with no active participants never fires), ``resolve_round`` is
    called. Returns the resolution result, or ``None`` when the round didn't
    resolve.
    """
    if encounter.pace_mode != PaceMode.READY:
        return None
    if encounter.status != RoundStatus.DECLARING:
        return None

    active_count = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).count()
    if active_count == 0:
        return None

    ready_count = CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        round_number=encounter.round_number,
        is_ready=True,
    ).count()
    if ready_count != active_count:
        return None

    return resolve_round(encounter)


def update_encounter_settings(  # noqa: PLR0913 - keyword-only tri-state settings kwargs
    encounter: CombatEncounter,
    *,
    stakes_level: str | None = None,
    risk_level: str | None = None,
    pace_mode: str | None = None,
    pace_timer_minutes: int | None = None,
    escalation_curve: EscalationCurve | None | object = _UNSET,
) -> CombatEncounter:
    """GM-driven mid-encounter settings change (#3383, curve #3552).

    Any subset of the fields may be given; omitted fields are left unchanged.
    ``escalation_curve`` is tri-state: omitted (``_UNSET``) leaves it alone,
    ``None`` clears it and tears down the room spike triggers, a curve sets it
    (the idempotent install in ``begin_declaration_phase`` picks it up next
    round). Applies decisions 5-6 of #3383: entering TIMED while DECLARING resets
    round_started_at; every call ends with a maybe_resolve_on_ready check
    (a no-op unless pace_mode is now READY and status is DECLARING).

    Stakes/risk changes gate only future opponent spawns and read-live
    call sites (EncounterAftermathRule lookup at completion,
    StakesEscalationModifier per-tick) - already-spawned CombatOpponent stat
    blocks are never retroactively rescaled (decision 1).
    """
    update_fields = []
    entering_timed = (
        pace_mode == PaceMode.TIMED
        and encounter.pace_mode != PaceMode.TIMED
        and encounter.status == RoundStatus.DECLARING
    )
    if stakes_level is not None:
        encounter.stakes_level = stakes_level
        update_fields.append("stakes_level")
    if risk_level is not None:
        encounter.risk_level = risk_level
        update_fields.append("risk_level")
    if pace_mode is not None:
        encounter.pace_mode = pace_mode
        update_fields.append("pace_mode")
    if pace_timer_minutes is not None:
        encounter.pace_timer_minutes = pace_timer_minutes
        update_fields.append("pace_timer_minutes")
    if escalation_curve is not _UNSET:
        encounter.escalation_curve = escalation_curve
        update_fields.append("escalation_curve")
    if entering_timed:
        encounter.round_started_at = timezone.now()
        update_fields.append("round_started_at")
    if update_fields:
        encounter.save(update_fields=update_fields)
    if escalation_curve is None:
        from world.combat.escalation import remove_escalation_room_triggers  # noqa: PLC0415

        remove_escalation_room_triggers(encounter)
    maybe_resolve_on_ready(encounter)
    return encounter


@transaction.atomic
def resolve_round(  # noqa: PLR0915 - orchestration function; already at the
    # single-helper-call budget (see _fire_round_start), and the #1899
    # climactic-moment guard is one more mandatory statement past the limit.
    encounter: CombatEncounter,
    *,
    defense_check_fn: PerformCheckFn | None = None,
    defense_check_type: CheckType | None = None,
    offense_check_fn: PerformCheckFn | None = None,
) -> RoundResolutionResult:
    """Orchestrate a full combat round: detect combos -> resolve -> consequences.

    High-level flow:
    1. Validate encounter is in ``DECLARING`` status, transition to ``RESOLVING``.
    2. Detect available combos from declared actions. Note: combo upgrades must
       happen during DECLARING phase via ``upgrade_action_to_combo``. The
       detection here is informational — it reports what combos were available
       and which actions were upgraded (``combo_upgrade != null``).
    3. Iterate resolution order (speed-rank sorted PCs and NPCs).
       - For each **PC**: resolve focused action against target opponent.
         If the action has a ``combo_upgrade``, apply bonus damage with soak
         bypass. Otherwise derive the offense_check_type from the declared
         technique's action_template and route through resolve_combat_technique.
         Apply fatigue after each action.
       - For each **NPC**: resolve each targeted PC's defensive check.
         Process knockout/death transitions and apply conditions.
       - After the resolution pass, a ``{name} holds back.`` line is broadcast
         for every ACTIVE PC in the order with no declaration this round,
         under TIMED and MANUAL pace only (#3552).
    4. Post-pass: resolve deferred RoundChallengeDeclarations in initiative
       order (reusing the round's resolution_order). Each participant's
       eligibility is re-validated via get_available_actions; ineligible
       declarations are skipped. Bridge rows for the round are deleted inside
       the same atomic block. Resolved outcomes populate ``challenge_outcomes``
       on the return value.
    4b. Post-pass: resolve clashes — detect new clash opportunities from the
       round's declared PC + NPC actions (creates Clash rows), then drive one
       round per active Clash. Gather ClashContributionDeclaration rows,
       build PreparedClashContribution objects, and call run_clash_round for
       each. Clean up all declarations for the round. Clash round outcomes
       populate ``clash_outcomes`` on the return value.
    5. Advance bleed-out: each participant with an active Bleeding-Out condition
       rolls its stage resist check; terminal-stage failure marks life_state=DEAD.
    6. After all actions: check boss phase transitions for boss-tier opponents.
    7. Check encounter completion (all opponents defeated or all PCs down).
    8. Transition encounter to ``BETWEEN_ROUNDS`` or ``COMPLETED``.

    Args:
        encounter: The combat encounter to resolve.
        defense_check_fn: Optional ``perform_check`` override for PC defense.
        defense_check_type: The CheckType used for defensive rolls.
        offense_check_fn: Optional ``perform_check`` override for PC offense.
            The offense_check_type is now sourced from ``resolve_cast_check_type``
            (the caster's personal check, falling back to the declared technique's
            action_template.check_type only when unprovisioned, ADR-0096) — it is
            no longer passed externally.

    Returns:
        ``RoundResolutionResult`` with outcomes and phase transitions.
    """
    _block_if_participant_mid_audere_majora_crossing(encounter)

    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if enc.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot resolve round: encounter status is "
            f"'{enc.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # NPC-selection wiring-gap fallback (#2637 design 8): select_npc_actions
    # has zero production callers outside the simulation harness in v1 — no
    # Action/command/task calls it before resolve_round. Auto-select here,
    # while status is still DECLARING (select_npc_actions requires it), when
    # this round has no NPC selection of EITHER shape yet (a normal
    # CombatOpponentAction OR a wind-up's PendingOpponentAttack) — a
    # conservative, idempotent fallback: any explicit prior selection (staff,
    # simulation, tests) is left alone.
    already_selected = (
        CombatOpponentAction.objects.filter(
            opponent__encounter=enc,
            round_number=enc.round_number,
        ).exists()
        or PendingOpponentAttack.objects.filter(
            encounter=enc,
            declared_round=enc.round_number,
        ).exists()
    )
    if not already_selected:
        select_npc_actions(enc)

    # Berserk compulsion (#2845): rage-driven participants who declared nothing
    # get their simplest damaging technique auto-declared. Idempotent — a
    # participant who steered their own rage (declared an attack) is skipped.
    from world.combat.berserk_compulsion import select_berserk_actions  # noqa: PLC0415

    select_berserk_actions(enc)

    enc.status = RoundStatus.RESOLVING
    enc.save(update_fields=["status"])

    round_number = enc.round_number
    result = RoundResolutionResult(round_number=round_number)

    # --- Round-start lifecycle: emit event, drain upkeep, detect combos ---
    result.available_combos = _fire_round_start(enc, round_number)

    # --- Vulnerability window countdown (#2016) ---
    CombatOpponent.objects.filter(
        encounter=encounter,
        vulnerability_rounds_remaining__gt=0,
    ).update_with_reason(
        reason="issue #3817: intentional atomic write",
        vulnerability_rounds_remaining=F("vulnerability_rounds_remaining") - 1,
    )

    # --- Wind-up maturation (#2637 design 5): before the round's
    # CombatOpponentAction rows are queried below, so a matured wind-up's
    # synthesized action is picked up in the same pass. ---
    _mature_pending_opponent_attacks(enc, round_number)

    # --- Sustained-action maturation (#2705): same placement rationale as the
    # wind-up maturation above — before the round's CombatRoundAction rows are
    # queried below, so a held technique's cloned action is picked up by the
    # normal PC pipeline in this same pass. ---
    _mature_sustained_actions(enc, round_number)

    # --- Sustaining participants declared their commitment THIS round, not an
    # action to resolve THIS round (#2705, D2) — the CombatRoundAction row on
    # the board right now is that declaration, not something to run through
    # _resolve_actions. One query, no loop queries. ---
    sustaining_participant_ids = frozenset(
        SustainedAction.objects.filter(
            encounter=enc,
            declared_round=round_number,
        ).values_list("participant_id", flat=True)
    )

    # --- Build action lookups ---
    pc_actions: dict[int, CombatRoundAction] = {}
    for action in (
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            round_number=round_number,
        )
        .select_related(
            "participant",
            "participant__character_sheet",
            "focused_action",
            "focused_action__effect_type",
            "focused_action__action_template",
            "focused_action__action_template__check_type",
            "focused_opponent_target",
            "focused_ally_target__character_sheet__character",
            "combo_upgrade",
            "physical_passive",
            "social_passive",
            "mental_passive",
        )
        .prefetch_related(
            "physical_passive__condition_applications__condition",  # noqa: PREFETCH_STRING
            "social_passive__condition_applications__condition",  # noqa: PREFETCH_STRING
            "mental_passive__condition_applications__condition",  # noqa: PREFETCH_STRING
        )
    ):
        pc_actions[action.participant_id] = action

    # Upgrades are validated again after every declaration and late auto-action
    # has been materialized.  Never let a stale FK grant a combo rider.
    _revalidate_combo_upgrades(enc, round_number, pc_actions)

    npc_actions: dict[int, list[CombatOpponentAction]] = defaultdict(list)
    for npc_action in (
        CombatOpponentAction.objects.filter(
            opponent__encounter=encounter,
            round_number=round_number,
        )
        .select_related("opponent", "threat_entry")
        .prefetch_related(
            Prefetch(
                "targets",
                queryset=CombatParticipant.objects.select_related(
                    "character_sheet",
                ),
                to_attr="cached_targets",
            ),
            Prefetch(
                "opponent_targets",
                queryset=CombatOpponent.objects.all(),
                to_attr="cached_opponent_targets",
            ),
            Prefetch(
                "threat_entry__conditions_applied",
                to_attr="cached_conditions",
            ),
        )
    ):
        npc_actions[npc_action.opponent_id].append(npc_action)

    # --- Resolve in speed-rank order ---
    resolution_order = get_resolution_order(encounter)
    _resolve_passive_actions(encounter, pc_actions)
    _refresh_participant_trigger_handlers(encounter)
    _ensure_reactive_challenges(encounter, pc_actions)
    result.action_outcomes = _resolve_actions(
        resolution_order,
        pc_actions,
        npc_actions,
        defense_check_type,
        defense_check_fn,
        offense_check_fn,
        sustaining_participant_ids=sustaining_participant_ids,
    )

    # --- Held-back line (#3552): a PC in the order with nothing declared was
    # skipped silently under TIMED/MANUAL. Say so, with the other OUTCOME lines.
    _narrate_held_back(enc, resolution_order, pc_actions, sustaining_participant_ids)

    # --- Combo post-resolution: joint narration + discovery + use-count (#2017) ---
    result.action_outcomes = _process_combo_outcomes(
        result.action_outcomes,
        enc,
        round_number,
    )

    # --- Post-pass: deferred challenge declarations (in initiative order) ---
    result.challenge_outcomes = _resolve_declared_challenges(
        encounter,
        round_number,
        resolution_order,
    )

    # --- Post-pass: clash opportunity detection + per-round drivers ---
    result.clash_outcomes = _resolve_clashes(
        encounter,
        round_number,
        resolution_order,
    )

    # --- Break-bar assessment (#2016, diversity-weighted feeds #2642) ---
    # Runs AFTER the clash post-pass (not before, as pre-#2642) so the HOLD
    # feed can see this round's just-resolved LOCK-clash wins against the boss.
    assess_break_bar(encounter, result.action_outcomes)

    # --- Round-tick: decrement rounds_remaining, tick DoT, fire expiry events,
    # and advance bleed-out for every active participant / opponent.
    # tick_round_for_targets(timing="end") calls process_round_end then
    # advance_bleed_out for each target that has a sheet_data — covering all
    # active bleeding participants (superset of the old pre-filtered query).
    from world.vitals.services import tick_round_for_targets  # noqa: PLC0415

    active_participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    active_opponents_end = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).select_related("objectdb")
    end_targets = [p.character_sheet.character for p in active_participants]
    end_targets += [opp.objectdb for opp in active_opponents_end if opp.objectdb is not None]
    tick_round_for_targets(end_targets, timing="end")

    # --- Sent Flying explicit resolution (#2638): every unanswered marker
    # resolves now — plummet chain or hard impact. Deliberately AFTER the
    # round-tick pass (a literal ROUNDS/1 duration would race the generic
    # duration countdown above — see world.combat.sent_flying_content) and
    # BEFORE boss/completion status transitions, so a landing impact can still
    # affect this round's completion check. ---
    _resolve_sent_flying_markers(enc)

    # --- Boss phase transitions ---
    result.phase_transitions = _check_boss_transitions(encounter)

    # --- Check encounter completion ---
    # A DUEL may have already been completed mid-round by a YIELD maneuver
    # (yield_duel routes through complete_encounter). Re-fetch status to avoid
    # double-completing or flipping a COMPLETED duel back to BETWEEN_ROUNDS.
    enc.refresh_from_db(fields=["status"])
    if enc.status == RoundStatus.COMPLETED:
        result.encounter_completed = True
    elif enc.encounter_type == EncounterType.DUEL:
        # Duels have their own end conditions (mirror DEFEATED → winner; lethal
        # opponent DEFEATED / PC down). resolve_duel_end completes via the shared
        # seam and returns the encounter, or None if the duel is still ongoing.
        from world.combat.duels import resolve_duel_end  # noqa: PLC0415

        enc.round_started_at = None
        enc.save(update_fields=["round_started_at"])
        if resolve_duel_end(enc) is not None:
            result.encounter_completed = True
        else:
            enc.status = RoundStatus.BETWEEN_ROUNDS
            enc.save(update_fields=["status"])
    elif _check_encounter_completion(encounter):
        result.encounter_completed = True
        enc.round_started_at = None
        enc.save(update_fields=["round_started_at"])
        complete_encounter(enc, outcome=_classify_encounter_outcome(enc))
    else:
        # Note: round_number is NOT advanced here. begin_declaration_phase
        # handles incrementing round_number when transitioning from
        # BETWEEN_ROUNDS to DECLARING for the next round.
        enc.status = RoundStatus.BETWEEN_ROUNDS
        enc.round_started_at = None
        enc.save(update_fields=["status", "round_started_at"])
    encounter.refresh_from_db()

    return result
