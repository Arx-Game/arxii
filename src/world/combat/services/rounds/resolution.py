"""resolve_round: the round orchestrator."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Prefetch

from world.combat.constants import EncounterType, OpponentStatus, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
    CombatRoundAction,
    PendingOpponentAttack,
    SustainedAction,
)
from world.combat.services.boss.break_bar import assess_break_bar
from world.combat.services.combos.combo_outcome import _process_combo_outcomes
from world.combat.services.combos.combo_upgrade import _revalidate_combo_upgrades
from world.combat.services.combos.resolution_order import get_resolution_order
from world.combat.services.damage.challenges import _ensure_reactive_challenges
from world.combat.services.damage.passive_techniques import (
    _refresh_participant_trigger_handlers,
    _resolve_passive_actions,
)
from world.combat.services.encounter.completion import (
    _check_encounter_completion,
    complete_encounter,
)
from world.combat.services.encounter.encounter_outcome import _classify_encounter_outcome
from world.combat.services.encounter.state_ping import notify_encounter_changed_on_commit
from world.combat.services.npc.npc_selection import ensure_opponent_plans, select_npc_actions
from world.combat.services.npc.npc_targeting import attach_npc_action_targets
from world.combat.services.npc.sustained import _mature_sustained_actions
from world.combat.services.npc.windup import _mature_pending_opponent_attacks
from world.combat.services.rounds.action_resolution import _resolve_actions
from world.combat.services.rounds.boss_transitions import _check_boss_transitions
from world.combat.services.rounds.clash import _resolve_clashes
from world.combat.services.rounds.declared_challenges import _resolve_declared_challenges
from world.combat.services.rounds.held_back import _narrate_held_back
from world.combat.services.rounds.round_start import _fire_round_start
from world.combat.services.rounds.waiting_strikes import narrate_unanswered_waits
from world.combat.services.sent_flying.sent_flying import _resolve_sent_flying_markers
from world.combat.services.techniques.audere import _block_if_participant_mid_audere_majora_crossing
from world.combat.types import RoundResolutionResult
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.checks.models import CheckType
    from world.checks.types import CheckResult

    PerformCheckFn = Callable[..., CheckResult]


def _count_down_vulnerability_windows(encounter: CombatEncounter) -> None:
    """Take a round off every open vulnerability window in the encounter.

    Counts down on the identity-mapped instances, then writes them. A queryset
    update left every cached opponent reading the old count (``refresh_from_db``
    hands back the same instance), so the payload kept the window open and the
    opponent's next full ``save()`` wrote the old count back (#4784).
    """
    counting_down = list(
        CombatOpponent.objects.filter(encounter=encounter, vulnerability_rounds_remaining__gt=0)
    )
    for opponent in counting_down:
        opponent.vulnerability_rounds_remaining -= 1
    if counting_down:
        CombatOpponent.objects.bulk_update_with_reason(
            counting_down,
            ["vulnerability_rounds_remaining"],
            reason="issue #3817: intentional bulk write",
        )


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
            The offense check is now sourced from ``resolve_cast_check``
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
    # simulation, tests) is left alone. A move plan (#4607) also counts as a
    # selection. Either way, ensure_opponent_plans then plans any opponent a
    # partial prior selection left without a plan, so none stands idle.
    already_selected = (
        CombatOpponentAction.objects.filter(
            opponent__encounter=enc,
            round_number=enc.round_number,
        ).exists()
        or CombatOpponentMove.objects.filter(
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
    ensure_opponent_plans(enc)

    # Compulsions (#2845, #4802): a compelled PC whose declaration goes against the
    # compulsion rolls to resist it, and a failure replaces the declaration with the
    # compulsion attack. Then compelled participants who declared nothing get their
    # simplest damaging technique auto-declared; a participant who steered their own
    # rage (declared an attack) is skipped.
    from world.combat.compulsion import (  # noqa: PLC0415
        resolve_compulsions,
        select_compelled_actions,
    )

    resolve_compulsions(enc)
    select_compelled_actions(enc)

    enc.status = RoundStatus.RESOLVING
    enc.save(update_fields=["status"])

    round_number = enc.round_number
    result = RoundResolutionResult(round_number=round_number)

    # --- Round-start lifecycle: emit event, drain upkeep, detect combos ---
    result.available_combos = _fire_round_start(enc, round_number)

    # --- Vulnerability window countdown (#2016) ---
    _count_down_vulnerability_windows(encounter)

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
                "threat_entry__conditions_applied",
                to_attr="cached_conditions",
            ),
        )
    ):
        npc_actions[npc_action.opponent_id].append(npc_action)
    attach_npc_action_targets([row for rows in npc_actions.values() for row in rows])

    npc_moves: dict[int, CombatOpponentMove] = {
        move.opponent_id: move
        for move in CombatOpponentMove.objects.filter(
            opponent__encounter=encounter,
            round_number=round_number,
        )
    }

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
        npc_moves=npc_moves,
    )

    # --- Held-back line (#3552): a PC in the order with nothing declared was
    # skipped silently under TIMED/MANUAL. Say so, with the other OUTCOME lines.
    _narrate_held_back(enc, resolution_order, pc_actions, sustaining_participant_ids)
    # --- Waiting strikes that never fired (#4608): said once, at no cost.
    narrate_unanswered_waits(enc)

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
    # After the commit, so a map that refetches reads this round's outcome (#4644).
    notify_encounter_changed_on_commit(enc)

    return result
