"""Encounter completion, outcome classification, and aftermath."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from flows.constants import EventName
from flows.events.payloads import EncounterCompletedPayload
from world.combat import services as _svc
from world.combat.constants import (
    CombatAllegiance,
    EncounterOutcome,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    EncounterAftermathRule,
)
from world.combat.services.boss_and_social import _record_combat_consequence
from world.combat.services.foundations import delete_ephemeral_npc
from world.combat.services.pc_and_npc_actions import (
    _break_pending_sustained_actions,
    _cancel_pending_certain_death_if_abandoned,
)
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.audere import PendingAudereOffer
    from world.magic.audere_majora import PendingAudereMajoraOffer
    from world.scenes.models import Interaction

logger = logging.getLogger(__name__)


def _end_audere_kind_and_delete_offers(
    condition_name: str,
    end_fn: Callable[[ObjectDB], None],
    pending_offer_model: type[PendingAudereOffer | PendingAudereMajoraOffer],
    participant_targets: list[ObjectDB],
) -> None:
    """Revert one Audere-family condition for its holders and clear its pending offers.

    Extracted out of ``cleanup_completed_encounter`` (one call per kind) to keep
    that function's own branching simple -- this is Audere/Audere Majora's own
    per-kind unit of work, including the #4101 fix round 1 withheld-manifestation
    release for the Majora kind specifically.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.audere_majora import PendingAudereMajoraOffer  # noqa: PLC0415

    target_ids = set(
        ConditionInstance.objects.filter(
            target__in=participant_targets,
            condition__name=condition_name,
        ).values_list("target_id", flat=True)
    )
    for target in participant_targets:
        if target.pk in target_ids:
            end_fn(target)
    offers = pending_offer_model.objects.filter(character_sheet__character__in=participant_targets)
    if pending_offer_model is PendingAudereMajoraOffer:
        _release_and_delete_withheld_majora_offers(offers)
        offers.filter(manifestation_withheld=False).delete()
    else:
        offers.delete()


def _release_and_delete_withheld_majora_offers(offers: QuerySet[PendingAudereMajoraOffer]) -> None:
    """Lock, release, and delete each withheld-manifestation Majora offer, one row at a time.

    The gate opened with a GM present, promising a Crossing prompt that will now
    never exist (the encounter is ending unresolved) -- the held line must not
    be silently lost (#4101 fix round 1, I1). Goes through
    ``release_and_delete_withheld_offer`` (#4101 fix round 2, should-fix 4) --
    per-row ``select_for_update`` guards against a concurrent accept/decline
    already having consumed the same offer between this sweep's query and its
    own delete. ``offers`` is bounded to this encounter's own participants, so
    a per-row lock+release+delete is cheap. The non-withheld remainder is
    still bulk-deleted by the caller afterward -- only the withheld rows need
    this one-at-a-time treatment.
    """
    from world.magic.audere_majora import release_and_delete_withheld_offer  # noqa: PLC0415

    for offer_id in offers.filter(manifestation_withheld=True).values_list("pk", flat=True):
        release_and_delete_withheld_offer(offer_id)


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


def _classify_encounter_outcome(encounter: CombatEncounter) -> EncounterOutcome:
    """Classify a completing encounter (#876 spec §1).

    1. No ACTIVE opponents and no Hero Killer present → VICTORY. An unbeatable
       Hero Killer (#875) still ACTIVE and still hostile forbids VICTORY — but
       a Hero Killer won over (charmed/turned/calmed) counts as won over like
       any other enemy: social victory ends the fight too (#4091 fix round 2).
       A FLED (or otherwise non-ACTIVE) Hero Killer keeps the original "at any
       status forbids VICTORY" behavior.
    2. No ACTIVE participants and at least one FLED → FLED.
    3. Else → DEFEAT (catch-all: downed ACTIVE participants, or all-REMOVED).
    """
    # VICTORY hinges on ENEMY opponents only — an ALLY summon left standing is
    # part of the winning side, not a reason to withhold victory (#1584). A
    # won-over enemy (charmed, turned, calmed during THIS encounter — ruling
    # R1) does not count as hostile either (#4091).
    from world.combat.won_over import hostile_opponents_remain  # noqa: PLC0415

    any_active_opponents = hostile_opponents_remain(encounter)
    if not any_active_opponents:
        # Reaching this branch already proves no ACTIVE+stored-ENEMY opponent
        # (Hero Killer included) is still effectively hostile -- hostile_opponents_remain
        # just said so. So an ACTIVE Hero Killer found here is, by construction, won
        # over; exclude it from "present" (#4091 fix round 2). A FLED/DEFEATED/REMOVED
        # Hero Killer is untouched by that guarantee and still blocks VICTORY.
        hero_killer_present = (
            CombatOpponent.objects.filter(encounter=encounter, tier=OpponentTier.HERO_KILLER)
            .exclude(status=OpponentStatus.ACTIVE)
            .exists()
        )
        if not hero_killer_present:
            return EncounterOutcome.VICTORY
        # An unbeatable Hero Killer was on the field -- never a victory.
        # Fall through to FLED / DEFEAT classification below.

    statuses = set(
        CombatParticipant.objects.filter(encounter=encounter).values_list("status", flat=True)
    )
    no_active = ParticipantStatus.ACTIVE not in statuses
    if no_active and ParticipantStatus.FLED in statuses:
        return EncounterOutcome.FLED
    return EncounterOutcome.DEFEAT


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


def _broadcast_encounter_outcome(
    encounter: CombatEncounter, outcome: EncounterOutcome
) -> Interaction | None:
    """Assemble side labels and persist+broadcast the ceremonial OUTCOME line."""
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_encounter_outcome_narration,
    )
    from world.combat.won_over import won_over_labels  # noqa: PLC0415
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(encounter=encounter).select_related(
            "character_sheet__character"
        )
    )
    opponents = list(CombatOpponent.objects.filter(encounter=encounter))
    # Persona display name, not str(CombatParticipant) -> str(CharacterSheet)
    # ("Sheet for {key}") -- a player-facing line shows the face the character
    # is CURRENTLY presenting as, batched in one call (#4091 fix round 2).
    persona_names = persona_names_for_sheets(p.character_sheet_id for p in participants)

    def _label(participant: CombatParticipant) -> str:
        return persona_names.get(
            participant.character_sheet_id, participant.character_sheet.character.key
        )

    narration = render_encounter_outcome_narration(
        outcome=outcome,
        active_labels=[_label(p) for p in participants if p.status == ParticipantStatus.ACTIVE],
        fled_labels=[_label(p) for p in participants if p.status == ParticipantStatus.FLED],
        defeated_opponent_labels=[
            o.name
            for o in opponents
            if o.status == OpponentStatus.DEFEATED and o.allegiance == CombatAllegiance.ENEMY
        ],
        won_over=[(name, verb) for name, verb, _src in won_over_labels(encounter)],
    )
    # deliver_telnet=True: the top-level encounter outcome (including the
    # won-over clause) must reach a bare telnet session too (#4091 fix round 2,
    # #3807) -- unlike this function's other, per-action callers.
    return broadcast_action_outcome(encounter=encounter, narration=narration, deliver_telnet=True)


def _apply_aftermath_rules(
    encounter: CombatEncounter,
    outcome: EncounterOutcome,
    interaction: Interaction | None,
) -> None:
    """Per-PC graded aftermath via the authored (outcome, risk) cell (#876 §3).

    Mirrors _resolve_flee's pipeline: modifiers → select_consequence (theater
    included) → apply_resolution → record_consequence_outcome anchored to the
    encounter OUTCOME interaction. Legend, when authored, rides LEGEND_AWARD
    consequences in the pool — context.participants carries the PC's persona.

    context.interaction also carries the same OUTCOME interaction (#2987):
    LEGEND_AWARD reads it to open a WITNESS reaction window when the deed
    lands public and crime-tagged, so bystanders in the encounter's scene get
    a report/intervene/ignore choice on the same event this aftermath fires
    from.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    rule = (
        EncounterAftermathRule.objects.filter(outcome=outcome, risk_level=encounter.risk_level)
        .select_related("check_type", "consequence_pool")
        .first()
    )
    if rule is None or rule.consequence_pool_id is None:
        return

    affected_status = (
        ParticipantStatus.FLED if outcome == EncounterOutcome.FLED else ParticipantStatus.ACTIVE
    )
    affected = list(
        CombatParticipant.objects.filter(
            encounter=encounter, status=affected_status
        ).select_related("character_sheet__character")
    )
    consequences = resolve_pool_consequences(rule.consequence_pool)

    for participant in affected:
        sheet = participant.character_sheet
        character = sheet.character
        breakdown = _svc.collect_check_modifiers(sheet, rule.check_type, scene=encounter.scene)
        pending = select_consequence(
            character,
            rule.check_type,
            rule.base_difficulty,
            consequences,
            extra_modifiers=breakdown.total,
        )
        try:
            participants_ctx = [sheet.primary_persona]
        except Persona.DoesNotExist:
            participants_ctx = None
        apply_resolution(
            pending,
            ResolutionContext(
                character=character,
                scene=encounter.scene,
                participants=participants_ctx,
                interaction=interaction,
            ),
        )
        _record_combat_consequence(
            sheet,
            rule.check_type,
            rule.consequence_pool,
            pending,
            breakdown,
            interaction=interaction,
            summary=f"encounter aftermath ({outcome.label})",
        )


def _apply_opponent_aftermath_pools(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """Fire each overcome opponent's authored aftermath pool on PC victory (#876 §4, #4091).

    "Overcome" covers both a DEFEATED enemy and a WON_OVER one (charmed, turned
    or calmed into standing down rather than beaten down — Decision 10): the
    same per-opponent pool pays out either way. Deterministic (story-consequence
    semantics, like beat pools). Context follows the beats GLOBAL idiom: the
    opponent's ObjectDB when set, else an unsaved stub that is only
    identity-safe for non-character effects.
    """
    if outcome != EncounterOutcome.VICTORY:
        return

    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_pool_deterministically,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    qs = CombatOpponent.objects.filter(
        encounter=encounter,
        status__in=[OpponentStatus.DEFEATED, OpponentStatus.WON_OVER],
        aftermath_pool__isnull=False,
    ).select_related("aftermath_pool", "objectdb")
    for opponent in qs:
        character = opponent.objectdb or ObjectDB()  # unsaved stub — non-character effects only
        apply_pool_deterministically(
            pool=opponent.aftermath_pool,
            context=ResolutionContext(character=character, scene=encounter.scene),
        )


def _resolve_companion_defeats(encounter: CombatEncounter) -> None:
    """Resolve each defeated bonded companion's stakes-gated consequence (#3652).

    #1873 Decision 4 put this at completion rather than at the defeat moment:
    all round resolution finishes before consequences resolve, and a DEFEATED
    companion is never re-targeted mid-resolution. Runs before
    cleanup_completed_encounter because the die outcome destroys the
    companion's ObjectDB, and the cleanup sweeps read opponent.objectdb.

    Skipped for ABANDONED by its caller: administrative closure is not a fight,
    and a GM ending a scene must not kill anyone's companion.
    """
    from world.companions.services import (  # noqa: PLC0415
        narrate_companion_loss,
        resolve_bonded_companion,
        resolve_companion_defeat,
    )

    opponents = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.DEFEATED,
        allegiance=CombatAllegiance.ALLY,
        summoned_by__isnull=False,
    ).select_related("objectdb")
    for opponent in opponents:
        companion = resolve_bonded_companion(opponent)
        if companion is None:
            continue
        name = companion.name
        if resolve_companion_defeat(companion, encounter.risk_level):
            narrate_companion_loss(name, encounter.scene)


def _increment_completion_counters(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """encounters_won / encounters_lost / encounters_fled aggregates (#876 §7).

    A DUEL leaves both PCs as ACTIVE participants at completion (only the loser's
    mirror ``CombatOpponent`` is DEFEATED, never the loser's own participant row),
    so the generic ACTIVE→won rule would credit *both* duelists with a win. For a
    DUEL the win is credited solely to ``encounter.duel_winner`` and the loss to
    the other duelist; an abandoned duel (no ``duel_winner``) credits neither
    (#1182).

    Buckets participants by outcome and makes ONE group counter call per bucket
    (#3075) — everyone who fled, everyone who won, everyone who lost is a
    genuinely simultaneous moment, so a first-ever threshold achievement shares
    its Discovery across the whole bucket instead of going solely to whichever
    participant a per-sheet loop happened to process first. Buckets never share
    a stat, so no cross-bucket moment exists.
    """
    from world.combat.achievement_counters import (  # noqa: PLC0415
        STAT_KEY_ENCOUNTERS_FLED,
        STAT_KEY_ENCOUNTERS_LOST,
        STAT_KEY_ENCOUNTERS_WON,
        increment_combat_counter_for_group,
    )

    # Ordered by join order (#3319). Nothing player-facing rides on this: the bucket
    # lists go to ``increment_stat_for_group`` -> ``grant_achievement``, which puts the
    # first sheet in the primary ``Discovery.discovered_by_tenure`` FK and the rest in
    # ``shared_with_tenures``, and #3063 ruled that split invisible -- every member of a
    # group discovery reads identically as "shared". Unordered, though, the split fell
    # out of Postgres heap order, which shifts whenever ``_apply_aftermath_rules``
    # rewrites a participant row, and made the arbitrary choice unreproducible run to
    # run. Ordering by pk keeps it stable without making it mean anything.
    participants = (
        CombatParticipant.objects.filter(encounter=encounter)
        .select_related("character_sheet")
        .order_by("pk")
    )

    if encounter.encounter_type == EncounterType.DUEL:
        winner_sheet_id = encounter.duel_winner_id
        fled_sheets = []
        winner_sheets = []
        loser_sheets = []
        for participant in participants:
            if participant.status == ParticipantStatus.FLED:
                fled_sheets.append(participant.character_sheet)
            elif winner_sheet_id is None:
                continue  # Abandoned / mutual stop — no victor; credit neither.
            elif participant.character_sheet_id == winner_sheet_id:
                winner_sheets.append(participant.character_sheet)
            else:
                loser_sheets.append(participant.character_sheet)
        increment_combat_counter_for_group(fled_sheets, STAT_KEY_ENCOUNTERS_FLED)
        increment_combat_counter_for_group(winner_sheets, STAT_KEY_ENCOUNTERS_WON)
        increment_combat_counter_for_group(loser_sheets, STAT_KEY_ENCOUNTERS_LOST)
        return

    outcome_key = {
        EncounterOutcome.VICTORY: STAT_KEY_ENCOUNTERS_WON,
        EncounterOutcome.DEFEAT: STAT_KEY_ENCOUNTERS_LOST,
    }.get(outcome)

    fled_sheets = []
    outcome_sheets = []
    for participant in participants:
        if participant.status == ParticipantStatus.FLED:
            fled_sheets.append(participant.character_sheet)
        elif participant.status == ParticipantStatus.ACTIVE and outcome_key is not None:
            outcome_sheets.append(participant.character_sheet)
    increment_combat_counter_for_group(fled_sheets, STAT_KEY_ENCOUNTERS_FLED)
    if outcome_key is not None:
        increment_combat_counter_for_group(outcome_sheets, outcome_key)


def _emit_encounter_completed(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """Emit the ENCOUNTER_COMPLETED reactive hook (#876 §6).

    Downstream systems — stories, missions, achievements, Legend — subscribe
    via triggers. Never XP: combat does not award XP. Skips when no room
    (emit_event requires a location); mirrors the _emit_death_gate idiom.
    """
    room = encounter.room
    if room is None:
        logger.debug(
            "Encounter %s completed with no room; skipping ENCOUNTER_COMPLETED emit.",
            encounter.pk,
        )
        return
    _svc.emit_event(
        EventName.ENCOUNTER_COMPLETED,
        EncounterCompletedPayload(
            encounter=encounter,
            outcome=str(outcome),
            scene=encounter.scene,
            room=room,
        ),
        location=room,
    )
