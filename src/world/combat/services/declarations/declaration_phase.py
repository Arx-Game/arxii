"""Opening the declaration phase."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from world.combat.constants import EncounterType, OpponentStatus, ParticipantStatus
from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
from world.combat.services.encounter.bonds import _dissolve_graduated_bonds
from world.combat.services.encounter.engagement import _ensure_combat_engagement
from world.combat.services.encounter.pulls import expire_pulls_for_round
from world.scenes.constants import RoundStatus


@transaction.atomic
def begin_declaration_phase(encounter: CombatEncounter) -> None:
    """Advance round_number by 1 and set status to DECLARING.

    Uses select_for_update to prevent concurrent calls.
    Raises ValueError if the encounter is not BETWEEN_ROUNDS.
    """
    from world.standoffs.services.state import is_in_standoff  # noqa: PLC0415

    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if is_in_standoff(enc):
        msg = "The standoff has not broken yet."
        raise ValueError(msg)
    if enc.status != RoundStatus.BETWEEN_ROUNDS:
        msg = (
            f"Cannot begin declaration phase: encounter status is "
            f"'{enc.get_status_display()}', expected 'Between Rounds'."
        )
        raise ValueError(msg)

    has_opponents = CombatOpponent.objects.filter(
        encounter=enc,
        status=OpponentStatus.ACTIVE,
    ).exists()
    if not has_opponents:
        msg = "Cannot begin declaration phase: no active opponents in encounter."
        raise ValueError(msg)

    # Belt-and-suspenders: reject a lethal PvP duel before declaration advances.
    if enc.encounter_type == EncounterType.DUEL:
        from world.combat.duels import assert_duel_lethality_valid  # noqa: PLC0415

        assert_duel_lethality_valid(enc)

    enc.round_number += 1
    enc.status = RoundStatus.DECLARING
    enc.round_started_at = timezone.now()
    enc.save(update_fields=["round_number", "status", "round_started_at"])

    # #3567: a new round burns one tick of the running beat's scene clock. The
    # selector resolves the beat; a scene with no running beat or no open clock
    # is a no-op. The fill's completion is scheduled on_commit by the service.
    from world.scenes.clock_services import tick_scene_clock  # noqa: PLC0415

    tick_scene_clock(enc.scene)

    # Reaction economy (#2639): every participant's reaction budget refills
    # each round. A raw queryset .update() would bypass the SharedMemoryModel
    # identity map — any already-cached CombatParticipant instance (e.g. one
    # a caller is still holding) would keep reading its stale pre-reset value
    # forever, since refresh_from_db() on an idmapper model returns the SAME
    # cached instance rather than re-hydrating it from the row. Mutate the
    # identity-mapped instances directly, then persist with one bulk_update
    # query — correct in-memory state AND a single query, not a per-
    # participant save() loop.
    reset_participants = list(CombatParticipant.objects.filter(encounter=enc))
    for reset_participant in reset_participants:
        reset_participant.reactions_used = 0
        reset_participant.hops_used = 0
        # The dodge plan is per round (#4676): dodge again, in place, until set.
        reset_participant.dodge_enabled = True
        reset_participant.dodge_landing = None
    if reset_participants:
        CombatParticipant.objects.bulk_update_with_reason(
            reset_participants,
            ["reactions_used", "hops_used", "dodge_enabled", "dodge_landing"],
            reason="issue #3817: intentional bulk write",
        )

    # --- Round-start per-participant upkeep: DoT tick + engagement ensure ---
    from world.vitals.services import tick_round_for_targets  # noqa: PLC0415

    active_participants_start = CombatParticipant.objects.filter(
        encounter=enc,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    active_opponents_start = CombatOpponent.objects.filter(
        encounter=enc,
        status=OpponentStatus.ACTIVE,
    ).select_related("objectdb")
    start_targets = [p.character_sheet.character for p in active_participants_start]
    start_targets += [opp.objectdb for opp in active_opponents_start if opp.objectdb is not None]
    tick_round_for_targets(start_targets, timing="start")

    for p in active_participants_start:
        # Permanent idempotency safety net: any participant that reached this
        # point without a combat engagement (however they were created) gets
        # one ensured here so all downstream engagement-dependent paths are safe.
        _ensure_combat_engagement(p)

    # --- Escalation tick (#872): opted-in encounters build pressure each round ---
    from world.combat.escalation import (  # noqa: PLC0415
        apply_escalation_tick,
        install_escalation_room_triggers,
    )

    if enc.escalation_curve is not None:
        install_escalation_room_triggers(enc)
        apply_escalation_tick(enc)
        # Emotional conditions feed intensity (#4739): one surge per player character per
        # round, the sum of their conditions' current-stage intensity_per_round.
        from world.combat.condition_surges import (  # noqa: PLC0415
            apply_condition_intensity_surges,
        )

        apply_condition_intensity_surges(enc)

    # --- Mentor's Vow (#1165): persist graduated bond dissolution at round start ---
    # Bonds that have graduated (adjusted party leveled into band) are dissolved
    # here so future reads via effective_combat_level skip them cleanly.
    _dissolve_graduated_bonds(enc)

    # Spec A §3.8 + §7.4 lines 2031–2039: expire pulls for the previous
    # round *after* round_number has advanced so the < comparison catches
    # the old rows. recompute_max_health_with_threads runs per affected
    # participant inside expire_pulls_for_round (clamp-not-injure).
    expire_pulls_for_round(enc)
    # Refresh the caller's instance so it reflects the new state.
    encounter.refresh_from_db()
