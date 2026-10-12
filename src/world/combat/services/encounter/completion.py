"""Encounter completion, cleanup, and disconnect pausing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.combat import services as _svc
from world.combat.constants import EncounterOutcome, ParticipantStatus
from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
from world.combat.services.encounter.aftermath import (
    _apply_aftermath_rules,
    _apply_opponent_aftermath_pools,
)
from world.combat.services.encounter.companion_defeat import _resolve_companion_defeats
from world.combat.services.encounter.completion_counters import _increment_completion_counters
from world.combat.services.encounter.encounter_outcome import _emit_encounter_completed
from world.combat.services.encounter.npc_identity import delete_ephemeral_npc
from world.combat.services.rounds.certain_death import _cancel_pending_certain_death_if_abandoned
from world.combat.services.rounds.sustained_break import _break_pending_sustained_actions
from world.combat.services.techniques.audere import _end_audere_kind_and_delete_offers
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def cleanup_completed_encounter(encounter: CombatEncounter) -> None:
    """Delete encounter-ephemeral CombatNPC ObjectDBs. Persistent NPCs and PCs
    are never touched. Layer 5 of the multi-layer guard: defensive re-check
    before each delete in case a corrupt row escaped Layers 1–4.

    CombatOpponent rows are preserved (historical record). Only the ephemeral
    ObjectDB is destroyed, via ``delete_ephemeral_npc`` — which also nulls the
    cached ``CombatOpponent.objectdb`` reference, since ``ObjectDB.delete()``'s
    own SET_NULL update bypasses the identity map (#4091 fix round 2).

    Also breaks any still-pending PC ``SustainedAction`` for this encounter
    (#2705 adversarial review, Fix 3) — see ``_break_pending_sustained_actions``.

    A WON_OVER opponent with an open bind window (Decision 19, R3: a charmed
    nameless foe whose charmer is still in the room) is skipped here — the
    body stays alive for binding and is deleted later by
    ``release_closed_bind_windows()`` or ``release_won_over_npcs_in_room()``.
    """
    _break_pending_sustained_actions(encounter)

    # Sweep covenant rite buffs for this encounter (stamps completed_at on the
    # rite instances in addition to removing their granted condition).
    from world.covenants.services import complete_rites_for_encounter  # noqa: PLC0415

    complete_rites_for_encounter(encounter=encounter)

    # Generically expire any remaining UNTIL_END_OF_COMBAT conditions on the
    # encounter's participants and opponents. The rite sweep above already
    # removed its own (rite-granted) buffs, so this is idempotent for those;
    # it catches every other end-of-combat condition (e.g. technique-applied)
    # that nothing else expires. Runs before ephemeral NPC deletion so the
    # sweep observes those targets too.
    from world.conditions.services import expire_end_of_combat_conditions  # noqa: PLC0415

    # No status filter: includes REMOVED participants too, matching the backstop
    # loop below (#4098 fix round 1) — a certain death must resolve even for a
    # participant who left the encounter early.
    participants = list(
        CombatParticipant.objects.filter(encounter=encounter).select_related(
            "character_sheet__character"
        )
    )
    participant_targets = [p.character_sheet.character for p in participants]
    opponent_targets = [
        opp.objectdb
        for opp in CombatOpponent.objects.filter(encounter=encounter).select_related("objectdb")
    ]

    # Abandoned encounters cancel any pending certain death instead of applying it
    # (#4098 owner ruling). This MUST run before the Audere-ending loop just below —
    # see _cancel_pending_certain_death_if_abandoned's docstring for why.
    _cancel_pending_certain_death_if_abandoned(encounter, participants)

    # End Audere and Audere Majora BEFORE the generic condition sweep (#873, #543):
    # the sweep would strip the condition without reverting the engagement intensity
    # modifier or anima-pool expansion — only end_audere reverts those. Also delete
    # any unanswered pending offers; the gate dies with the encounter.
    #
    # Note: end_audere reverts intensity modifier + anima-pool expansion;
    # end_audere_majora only removes the condition (no modifier reversal needed).
    # The loop preserves this by calling the per-kind end_fn as-is.
    from world.magic.audere import (  # noqa: PLC0415
        AUDERE_CONDITION_NAME,
        AUDERE_MAJORA_CONDITION_NAME,
        PendingAudereOffer,
        end_audere,
    )
    from world.magic.audere_majora import (  # noqa: PLC0415
        PendingAudereMajoraOffer,
        end_audere_majora,
    )

    for condition_name, end_fn, pending_offer_model in [
        (AUDERE_CONDITION_NAME, end_audere, PendingAudereOffer),
        (AUDERE_MAJORA_CONDITION_NAME, end_audere_majora, PendingAudereMajoraOffer),
    ]:
        _end_audere_kind_and_delete_offers(
            condition_name, end_fn, pending_offer_model, participant_targets
        )

    expire_end_of_combat_conditions(participant_targets + opponent_targets)

    # Settle round-counted effects into wall-clock expiries (#4120). Rounds only
    # tick in combat, so a ROUNDS condition that outlives the fight would freeze.
    # Runs before the certain-death backstop and ephemeral NPC deletion: rows on
    # bodies that outlive combat must be converted while those bodies still exist.
    from world.conditions.services import settle_round_effects  # noqa: PLC0415

    settle_round_effects(participant_targets + opponent_targets)

    # Certain-death backstop (#4098 fix round 1): a deferred certain death
    # normally resolves in conditions.services._resolve_deferred_death_on_expiry
    # when the LAST death_deferred condition (Audere/Audere Majora) is removed
    # through the ordinary removal seam. But that seam doesn't always run before
    # the encounter ends — the round-duration countdown, an interaction removal,
    # or a damage interaction can all strip the condition without going through
    # it — which would leave death_certain_pending set forever. Call the same
    # resolution function directly for every participant sheet so the encounter's
    # own end is always a backstop. apply_pending_certain_death is idempotent and
    # no-ops when nothing is pending or the character is already dead, so this is
    # safe to call unconditionally. Reuses the sheets already loaded above —
    # never re-selects them.
    from world.vitals.services import apply_pending_certain_death  # noqa: PLC0415

    for participant in participants:
        apply_pending_certain_death(participant.character_sheet)

    # Combat-owned engagement teardown (#872): deleting the engagement discards
    # the transient escalation process modifiers. Must run AFTER end_audere
    # (which subtracts its own bonus from the row first — see comment above).
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import end_engagement  # noqa: PLC0415

    for target in participant_targets:
        end_engagement(target, EngagementType.COMBAT, source=encounter)

    # Escalation room-trigger teardown (#872): drop the spike triggers unless
    # another live escalating encounter still shares the room.
    from world.combat.escalation import remove_escalation_room_triggers  # noqa: PLC0415

    remove_escalation_room_triggers(encounter)

    from world.combat.won_over import bind_window_open  # noqa: PLC0415

    qs = CombatOpponent.objects.filter(
        encounter=encounter,
        objectdb_is_ephemeral=True,
    ).select_related("objectdb")
    for opp in qs:
        if bind_window_open(opp):
            continue  # Decision 19: deleted later by the sweep or scene finish

        delete_ephemeral_npc(opp)


def maybe_pause_encounter_for_disconnect(character_sheet: CharacterSheet) -> None:
    """Pause the character's live CombatEncounter, if any, on disconnect (#1899).

    CombatEncounter has no scale exception (it's inherently small-scale —
    PARTY_COMBAT/OPEN_ENCOUNTER/DUEL); every live encounter pauses. Reuses the
    existing is_paused field/semantics unchanged (soft flag; only blocks the
    TIMED-mode auto-resolve sweep, per its existing behavior).
    """
    participant = CombatParticipant.objects.filter(
        character_sheet=character_sheet,
        status=ParticipantStatus.ACTIVE,
        encounter__completed_at__isnull=True,
    ).first()
    if participant is None:
        return
    participant.encounter.is_paused = True
    participant.encounter.save(update_fields=["is_paused"])


def _check_encounter_completion(encounter: CombatEncounter) -> bool:
    """Return True if the encounter should be marked complete.

    Complete when either side is wiped: all opponents defeated, OR every active
    PC is "down" (cannot act — dead or incapacitated). A dying-but-conscious PC
    can still act, so the encounter is not lost while any PC can_act.
    """
    from world.combat.won_over import hostile_opponents_remain  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    # Only ENEMY opponents block victory; an ALLY summon staying active must not
    # keep the encounter open (#1584). A won-over enemy (charmed, turned, calmed
    # during THIS encounter — ruling R1) does not count as hostile either (#4091).
    all_opponents_down = not hostile_opponents_remain(encounter)

    active_participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")

    all_pcs_down = not any(can_act(p.character_sheet) for p in active_participants)

    return all_opponents_down or all_pcs_down


@transaction.atomic
def complete_encounter(encounter: CombatEncounter, *, outcome: EncounterOutcome) -> None:
    """Single completion seam for round resolution and the GM end endpoint (#876).

    Order: persist flip → Narrator OUTCOME interaction → aftermath (anchored to
    that interaction, before ephemeral-NPC cleanup) → opponent aftermath pools
    → companion defeat resolution (#3652) → counters → completion event →
    won-over snapshot (#4091) → cleanup → acute-peril scene-round hand-off →
    aftermath digest (#3551).
    ABANDONED is administrative closure: skips aftermath, opponent pools,
    companion defeats, and counters, but still narrates, emits, cleans up, and
    delivers the aftermath digest.

    Atomic so a bare caller (the GM end endpoint) cannot strand a COMPLETED
    flip with the aftermath/cleanup tail skipped — the double-completion guard
    would otherwise block any retry. Inside resolve_round it is a savepoint.
    """
    if encounter.status == RoundStatus.COMPLETED:
        msg = f"Encounter {encounter.pk} is already completed."
        raise ValueError(msg)

    encounter.status = RoundStatus.COMPLETED
    encounter.outcome = outcome
    encounter.completed_at = timezone.now()
    encounter.save(update_fields=["status", "outcome", "completed_at"])

    if outcome == EncounterOutcome.VICTORY:
        from world.combat.won_over import stamp_won_over_opponents  # noqa: PLC0415

        stamp_won_over_opponents(encounter)

    interaction = _svc._broadcast_encounter_outcome(encounter, outcome)  # noqa: SLF001 (test patch seam)

    if outcome != EncounterOutcome.ABANDONED:
        _apply_aftermath_rules(encounter, outcome, interaction)
        _apply_opponent_aftermath_pools(encounter, outcome)
        _resolve_companion_defeats(encounter)
        _increment_completion_counters(encounter, outcome)

    from world.combat.beat_wiring import install_encounter_beat_trigger  # noqa: PLC0415

    install_encounter_beat_trigger(encounter)
    _emit_encounter_completed(encounter, outcome)

    # Read the won-over rows while the bodies still exist (#4091 final review):
    # cleanup deletes ephemeral WON_OVER bodies, cascading their allegiance
    # instances away, so a digest read after it would drop every calmed mook.
    # The rest of the digest must stay after cleanup (it reports the conditions
    # a PC carries OUT of the fight and the peril hand-off), so only this part moves.
    from world.combat.won_over import won_over_snapshot  # noqa: PLC0415

    won_over = won_over_snapshot(encounter)
    cleanup_completed_encounter(encounter)
    # Survivors' holds as cleanup left them (an UNTIL_END_OF_COMBAT hold is gone).
    from world.combat.won_over import refresh_won_over_holds  # noqa: PLC0415

    won_over = refresh_won_over_holds(encounter, won_over)
    _hand_off_acute_peril_to_scene_round(encounter)

    from world.combat.aftermath import deliver_aftermath_digests  # noqa: PLC0415

    deliver_aftermath_digests(encounter, won_over=won_over)


def _hand_off_acute_peril_to_scene_round(encounter: CombatEncounter) -> None:
    """After combat ends, ensure any participant still Bleeding-Out or Plummeting is
    covered by a scene round so the peril keeps ticking (Task 6 — #1466).

    Guards:
    - Only PC participants (``CombatParticipant``), never NPC opponents.
    - Skip characters who are somehow still in another active encounter (paranoid guard).
    """
    from world.combat.aftermath import has_acute_peril  # noqa: PLC0415
    from world.combat.round_context import resolve_combat_round_context  # noqa: PLC0415
    from world.scenes.round_services import ensure_round_for_acute_condition  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(encounter=encounter).select_related(
            "character_sheet__character"
        )
    )
    for participant in participants:
        sheet = participant.character_sheet
        if not has_acute_peril(sheet):
            continue
        # Paranoid guard: skip if the character is already in another active encounter.
        if resolve_combat_round_context(sheet) is not None:
            continue
        ensure_round_for_acute_condition(sheet)


def end_encounter(encounter: CombatEncounter) -> CombatEncounter:
    """GM force-end: completes as ABANDONED (#876 §8)."""
    complete_encounter(encounter, outcome=EncounterOutcome.ABANDONED)
    return encounter
