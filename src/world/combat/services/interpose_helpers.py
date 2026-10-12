"""Interpose challenge helpers, leave/remove, sent-flying catch and trigger, declared challenges."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q

from world.combat import services as _svc
from world.combat.constants import (
    ENTITY_TYPE_PC,
    REACTIONS_PER_ROUND,
    CombatAllegiance,
    CombatManeuver,
    EncounterOutcome,
    EncounterType,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    PendingOpponentAttack,
    RoundChallengeDeclaration,
)
from world.combat.services.completion import (
    _check_encounter_completion,
    _classify_encounter_outcome,
    complete_encounter,
)
from world.combat.services.declare_action import _broadcast_windup_fizzled
from world.combat.services.foundations import remove_participant
from world.combat.services.npc_round_and_damage import _break_engagement_lock_on_defeat
from world.combat.services.windup_and_attacks import (
    _broadcast_sent_flying_catch,
    _broadcast_sent_flying_launch,
    _clear_sent_flying_marker,
)
from world.magic.models.soulfray import SoulfrayConfig
from world.magic.services.anima import deduct_anima
from world.mechanics.types import ChallengeResolutionResult
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from typeclasses.characters import Character
    from world.areas.positioning.models import Position
    from world.checks.types import CheckResult
    from world.magic.models import Technique
    from world.magic.models.anima import CharacterAnima
    from world.mechanics.models import ObjectProperty

logger = logging.getLogger(__name__)


@transaction.atomic
def leave_encounter(participant: CombatParticipant) -> None:
    """Allow a participant to voluntarily leave an Open Encounter between rounds.

    Unlike flee (a check-gated exit), this is unconditional. If the departing
    participant is the last active participant, the encounter completes as ABANDONED.

    Raises ValueError when:
    - the encounter is not in BETWEEN_ROUNDS status,
    - the encounter type is not OPEN_ENCOUNTER, or
    - the participant is not ACTIVE.
    """
    from world.combat.berserk_compulsion import reject_if_berserk  # noqa: PLC0415

    reject_if_berserk(participant, "leave")
    enc = CombatEncounter.objects.select_for_update().get(pk=participant.encounter_id)
    if enc.status != RoundStatus.BETWEEN_ROUNDS:
        msg = (
            f"Cannot leave: encounter status is "
            f"'{enc.get_status_display()}', expected 'Between Rounds'."
        )
        raise ValueError(msg)
    if enc.encounter_type != EncounterType.OPEN_ENCOUNTER:
        msg = (
            f"Cannot leave: encounter type is "
            f"'{enc.get_encounter_type_display()}', expected 'Open Encounter'."
        )
        raise ValueError(msg)
    # Re-read participant under the same transaction lock to avoid stale status reads.
    participant = CombatParticipant.objects.select_for_update().get(pk=participant.pk)
    if participant.status != ParticipantStatus.ACTIVE:
        msg = f"Cannot leave: participant status is '{participant.status}'."
        raise ValueError(msg)

    remove_participant(participant)

    any_active = CombatParticipant.objects.filter(
        encounter=enc,
        status=ParticipantStatus.ACTIVE,
    ).exists()
    if not any_active:
        complete_encounter(enc, outcome=EncounterOutcome.ABANDONED)


def remove_opponent(opponent: CombatOpponent) -> None:
    """Pull an opponent out of a live encounter (GM action, #3382).

    Reuses the defeat teardown seam minus defeat consequences: no legend/loot/
    aftermath, no narrated defeat. Raises ValueError if the opponent is not
    ACTIVE (already defeated/fled/removed — nothing to tear down twice).
    """
    from world.combat.constants import LockBreakReason  # noqa: PLC0415

    if opponent.status != OpponentStatus.ACTIVE:
        msg = f"Opponent {opponent.pk} is not ACTIVE (status={opponent.status})."
        raise ValueError(msg)

    opponent.status = OpponentStatus.REMOVED
    opponent.save(update_fields=["status"])

    # Break the active engagement lock immediately, same as a defeat teardown
    # (decision 2) — a GM pull is a harder cut than fleeing, not a softer one.
    _break_engagement_lock_on_defeat(opponent, reason=LockBreakReason.REMOVED)

    # Fizzle any pending wind-up this opponent had committed to — it never
    # deletes the CombatOpponent row (decision 5), so CASCADE never fires and
    # a stale PendingOpponentAttack would otherwise still resolve next round.
    for pending in PendingOpponentAttack.objects.filter(opponent=opponent):
        _broadcast_windup_fizzled(pending, reason="is called off")
        pending.delete()

    encounter = opponent.encounter
    if encounter.status != RoundStatus.COMPLETED and _check_encounter_completion(encounter):
        complete_encounter(encounter, outcome=_classify_encounter_outcome(encounter))


def _try_catch_sent_flying(participant: CombatParticipant) -> Character | None:
    """Find and fire the first eligible armed INTERPOSE to catch a Sent Flying victim.

    Same query shape as :func:`_try_interpose` (an armed INTERPOSE this round
    whose ``focused_ally_target`` is *participant* or ``None``), restricted to
    ACTIVE participants and excluding self-interpose. The fire gate is
    budget-only — ``REACTIONS_PER_ROUND`` via the interposer's
    ``reactions_used`` (#2639) — and deliberately never calls
    ``dispatch_interpose``/the mundane or technique challenge chain: that
    machinery grades HOW MUCH of a landing hit's *amount* a block reduces,
    which has no meaning for a mid-air catch (a binary rescue, not gradeable
    damage mitigation). "Fires" here means the SAME thing
    ``_dispatch_interpose_action``'s docstring documents for the mundane path:
    an attempt that clears budget, independent of any roll. Only one guardian
    is ever queried (the first eligible), so
    ``combat.constants.ABSORPTION_CAP_PER_MOMENT`` — built for multiple
    interceptors answering ONE ``DamagePreApplyPayload`` — has no second
    attempt to cap here; not consulted (documented v1 scope, #2638).

    Returns the catching Character on fire, or None (no eligible/budget-
    exhausted guardian (who is told privately, #3574): the marker stays for
    explicit resolution).
    """
    encounter = participant.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return None

    # Q(...) | Q(...), not `focused_ally_target__in=[participant, None]`: the
    # latter silently drops the None entry (Django compiles field__in with a
    # None member to a bare `IN (x)`, never `x OR field IS NULL`) — see the
    # bug-fix note on _try_interpose's identical query, discovered while
    # writing this sibling (#2638).
    action = (
        CombatRoundAction.objects.filter(
            Q(focused_ally_target=participant) | Q(focused_ally_target__isnull=True),
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            participant__status=ParticipantStatus.ACTIVE,
        )
        .exclude(participant=participant)
        .select_related("participant__character_sheet__character")
        .first()
    )
    if action is None:
        return None

    interposer = action.participant
    if interposer.reactions_used >= REACTIONS_PER_ROUND:
        _narrate_reaction_declined(
            interposer.character_sheet.character,
            participant.character_sheet.character,
            cap=False,
        )
        return None

    interposer.reactions_used += 1
    interposer.save(update_fields=["reactions_used"])
    return interposer.character_sheet.character


def _trigger_sent_flying(
    participant: CombatParticipant,
    npc_action: CombatOpponentAction,
    damage: int,
) -> None:
    """Apply the Sent Flying marker and consult the reaction seam (#2638).

    Fires when a ``sends_flying`` ThreatPoolEntry's attack lands damage > 0 on
    a PC participant (called from ``_resolve_npc_action_on_target``). Applies
    the seeded marker, stamps the triggering damage onto
    ``CombatParticipant.sent_flying_damage`` (the v1 carrier — see that
    field's help text), dual-dispatches the produced-moment narration, then
    IMMEDIATELY consults :func:`_try_catch_sent_flying`. A landed catch clears
    the marker and celebrates; otherwise the marker is left in place, silent,
    for :func:`_resolve_sent_flying_markers` at end of round.
    """
    from world.combat.sent_flying_content import SENT_FLYING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    character = participant.character_sheet.character
    try:
        template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        # Unseeded content (mirrors _ensure_interpose_challenges' warn-and-skip
        # shape) — a dev/test environment that never ran ensure_sent_flying_content.
        return

    apply_condition(character, template)
    participant.sent_flying_damage = damage
    participant.save(update_fields=["sent_flying_damage"])
    _broadcast_sent_flying_launch(participant)

    catcher = _try_catch_sent_flying(participant)
    if catcher is None:
        return
    _clear_sent_flying_marker(participant, character, template)
    _broadcast_sent_flying_catch(participant, npc_action, catcher)


def end_encounter(encounter: CombatEncounter) -> CombatEncounter:
    """GM force-end: completes as ABANDONED (#876 §8)."""
    complete_encounter(encounter, outcome=EncounterOutcome.ABANDONED)
    return encounter


def _resolve_declared_challenges(
    encounter: CombatEncounter,
    round_number: int,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
) -> list[ChallengeResolutionResult]:
    """Post-pass: resolve RoundChallengeDeclarations in participant initiative order.

    Called after all combat-action resolution for the round.  Fetches bridge rows,
    orders them to match the existing resolution_order for PC participants, resolves
    each character's declared challenge (re-validating eligibility via
    get_available_actions), and deletes all bridge rows for the round.

    Ineligible-skip: if get_available_actions returns no action matching the
    declared (challenge_instance_id, approach_id), the declaration is silently
    skipped — no CharacterChallengeRecord is created and no exception is raised.
    This mirrors dispatch-time security: declared state may be stale if a
    character lost their capability between declaration and resolution.

    The delete of bridge rows runs inside the caller's @transaction.atomic so it
    is consistent with the rest of round resolution.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415
    from world.scenes.round_services import (  # noqa: PLC0415
        ChallengeResolutionRequest,
        resolve_challenge_declarations,
    )
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    declarations = list(
        RoundChallengeDeclaration.objects.filter(
            encounter=encounter,
            round_number=round_number,
        ).select_related(
            "participant",
            "participant__character_sheet",
            "challenge_instance",
            "challenge_instance__location",
            "challenge_approach",
        )
    )

    if not declarations:
        return []

    # Build participant_id → declaration map for O(n) ordering.
    decl_by_participant: dict[int, RoundChallengeDeclaration] = {
        d.participant_id: d for d in declarations
    }

    # Order by the same resolution_order combat uses for PC participants.
    # NPCs never declare challenges, so only ENTITY_TYPE_PC entries matter.
    ordered: list[RoundChallengeDeclaration] = []
    for entity_type, entity in resolution_order:
        if entity_type != ENTITY_TYPE_PC:
            continue
        if not isinstance(entity, CombatParticipant):
            continue
        decl = decl_by_participant.pop(entity.pk, None)
        if decl is not None:
            ordered.append(decl)

    # Any declarations for participants not in resolution_order (e.g. DYING without
    # final-round) come after, preserving their insertion order.
    ordered.extend(decl_by_participant.values())

    # Batched, not one active_persona_for_sheet call per declaration (#4091 fix
    # round 2) -- this builds the whole request list in one comprehension.
    persona_names = persona_names_for_sheets(
        decl.participant.character_sheet_id for decl in ordered
    )
    requests = [
        ChallengeResolutionRequest(
            character=decl.participant.character_sheet.character,
            challenge_instance=decl.challenge_instance,
            approach=decl.challenge_approach,
            actor_label=persona_names.get(
                decl.participant.character_sheet_id,
                decl.participant.character_sheet.character.key,
            ),
        )
        for decl in ordered
    ]
    outcomes = resolve_challenge_declarations(
        requests,
        broadcast=lambda narration: broadcast_action_outcome(
            encounter=encounter, narration=narration
        ),
    )

    # Delete all bridge rows for this round inside the outer atomic block.
    RoundChallengeDeclaration.objects.filter(
        encounter=encounter,
        round_number=round_number,
    ).delete()

    return outcomes


def _narrate_reaction_declined(
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: object,
    *,
    cap: bool,
) -> None:
    """Tell a guardian, privately, why their armed guard did not fire (#3574).

    ``cap=False``: the guardian's own ``REACTIONS_PER_ROUND`` budget is spent.
    ``cap=True``: ``ABSORPTION_CAP_PER_MOMENT`` interceptors already answered
    this payload. No room line either way: ADR-0161 chose a silent no-op so the
    table never learns a guardian's budget, and this keeps that while the
    guardian themselves stops guessing. ``protected`` is whatever the fire
    seam holds (a participant character, an ally summon's objectdb, or the
    Sent Flying victim) and is only ever stringified.
    """
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    if cap:
        text = (
            f"Enough hands have already answered that blow; your guard over {protected} stays down."
        )
    else:
        text = (
            f"You have already spent your reaction this round; "
            f"{protected} takes the blow unguarded."
        )
    narrate_privately(interposer, text)


def _guardian_can_fire_technique_interpose(
    anima: CharacterAnima | None, cost: int, *, consented: bool
) -> bool:
    """True when a cost>0 technique-guardian reaction may fire.

    No pool at all means there's nothing to consent with. Otherwise: affordable
    fires unconditionally; unaffordable fires only when consented (#3573), which
    runs the guardian's anima into deficit (:func:`_settle_technique_interpose_cost`
    handles the actual debit).
    """
    if anima is None:
        return False
    return anima.current >= cost or consented


def _settle_technique_interpose_cost(  # noqa: PLR0913 - debit + accrue needs all of it
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    anima: CharacterAnima,
    cost: int,
    consented: bool,
    check_result: CheckResult | None,
) -> None:
    """Debit a firing technique guardian's anima and, if consented, accrue Soulfray.

    Split out of :func:`_try_technique_interpose` (#3573) purely to keep that
    function's branch count under the complexity budget - the debit-then-accrue
    sequencing is otherwise a single linear step in that function's flow.
    """
    encounter = action.participant.encounter
    deficit = deduct_anima(interposer, cost, lethal=encounter.is_lethal)
    if not consented:
        return
    _svc.accumulate_soulfray(
        character=interposer,
        anima=anima,
        deficit=deficit,
        soulfray_config=SoulfrayConfig.objects.cached_singleton(),
        check_result=check_result,
        lethal=encounter.is_lethal,
    )
    if deficit > 0:
        ally_name = (
            str(action.focused_ally_target.character_sheet.character)
            if action.focused_ally_target_id
            else str(protected)
        )
        _svc._broadcast_commitment_line(  # noqa: SLF001 (test patch seam)
            encounter,
            f"{interposer} tears at their own soul to hold the line over {ally_name}!",
        )


def _narrate_technique_interpose_fizzle(
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
) -> None:
    """Tell the guardian, then the room, that an unpaid protective technique fizzled (#3574).

    Private line carries the why (anima); the room line never carries a number.
    The mechanical no-op shape is unchanged: no roll, no charge, damage proceeds.
    """
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        technique_display_name,
    )
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    display_name = technique_display_name(interposer, technique)
    narrate_privately(
        interposer,
        f"Your {display_name} gutters for want of anima; {protected} takes the blow unguarded.",
    )
    _svc._broadcast_commitment_line(  # noqa: SLF001 (test patch seam)
        action.participant.encounter,
        f"{interposer} reaches to shield {protected}, and the working fails to catch.",
    )


def _redirect_away(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Broadcast the "away" redirect outcome — a silent deflection, no target hit."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    narration = f"{interposer.db_key} turns the blow aside — it goes wide, harming no one."
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _redirect_to_object(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    obj: ObjectDB,  # noqa: OBJECTDB_PARAM
    obj_property: ObjectProperty,
) -> None:
    """Detonate the declared volatile object: fire its pool, consume it, broadcast it.

    Position-anchored only — an object with no ``Position`` (shouldn't happen for
    a volatile object placed in a room with staged positions, but a defensive
    guard) degrades to "away" rather than firing at "everyone in the room."
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415
    from world.room_features.trap_services import fire_pool_at_characters  # noqa: PLC0415

    position = position_of(obj)
    if position is None:
        _redirect_away(encounter, interposer)
        return

    characters = _combatants_at_position(encounter, position)
    fire_pool_at_characters(
        obj_property.property.detonation.consequence_pool,
        characters,
        source_character=interposer,
    )
    obj_property.delete()

    narration = f"{interposer.db_key} hurls the blow into {obj.db_key} — it detonates!"
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _combatants_at_position(
    encounter: CombatEncounter,
    position: Position,
) -> list[ObjectDB]:  # noqa: OBJECTDB_PARAM
    """Every ACTIVE participant's character + ACTIVE opponent's objectdb at *position*.

    Single query against ``position.occupants`` (the ``ObjectPosition`` reverse
    relation) rather than calling ``current_position`` per combatant, to avoid a
    query-in-a-loop over the encounter's roster.
    """
    occupant_ids = set(position.occupants.values_list("objectdb_id", flat=True))

    characters: list[ObjectDB] = [
        p.character_sheet.character
        for p in CombatParticipant.objects.filter(
            encounter=encounter, status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet__character")
        if p.character_sheet.character_id in occupant_ids
    ]
    characters.extend(
        opp.objectdb
        for opp in CombatOpponent.objects.filter(
            encounter=encounter, status=OpponentStatus.ACTIVE
        ).select_related("objectdb")
        if opp.objectdb_id is not None and opp.objectdb_id in occupant_ids
    )
    return characters


def _fire_on_hit_pool(
    character: Character,
    source: object | None,
    pool: ConsequencePool,
) -> None:
    """Fire an attack's on-hit consequence pool (e.g. knockback) against the
    defender, then re-check the defender's landing position for hazards.

    Deterministic — no roll — since the attack's own hit already landed.
    ``source`` is expected to be the attacking ``CombatOpponent`` (the only
    caller wiring ``on_hit_pool`` today is ``resolve_npc_attack``, which
    passes ``source=opponent_action.opponent``); if it isn't a
    ``CombatOpponent`` with a placed ``objectdb``, there's no attacker
    Position to compute "away from actor" against, so this is a no-op.
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415
    from world.checks.consequence_resolution import apply_pool_deterministically  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.room_features.trap_services import check_traps_at_position  # noqa: PLC0415

    if not isinstance(source, CombatOpponent) or source.objectdb_id is None:
        return

    apply_pool_deterministically(
        pool=pool,
        context=ResolutionContext(character=source.objectdb, target=character),
    )

    landing_position = position_of(character)
    if landing_position is not None:
        check_traps_at_position(character, landing_position)


def _bind_interpose_challenges_any_ally(
    template: object,
    room: object,
    interposer_participant_id: int,
    active_participants_by_id: dict[int, CombatParticipant],
    active_ally_opponent_objectdbs: list[ObjectDB],
) -> None:
    """Bind a ChallengeInstance to every active participant and ALLY opponent.

    Every active participant except the interposer, plus every ALLY-allegiance
    ``CombatOpponent``'s objectdb (player summons/companion NPCs, #2207) — so a
    mundane guardian's :func:`dispatch_capability_reaction` finds a bound
    challenge instance when shielding a summon via the ANY-ALLY path. Note: this
    is the ONLY path that can bind a summon-ward — ``focused_ally_target`` FKs
    ``CombatParticipant``, so a summon can never be named as a *specific* ward
    (named-ally guarding of a summon is a follow-up).
    """
    from world.mechanics.models import ChallengeInstance  # noqa: PLC0415

    for part_id, part in active_participants_by_id.items():
        if part_id == interposer_participant_id:
            continue
        ally_char = part.character_sheet.character
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_char,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )

    for ally_objectdb in active_ally_opponent_objectdbs:
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_objectdb,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )


def _ensure_interpose_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind an Interpose ChallengeInstance to each protected ally.

    For every armed INTERPOSE ``CombatRoundAction`` this round, idempotently
    ``get_or_create`` an active+revealed ``ChallengeInstance`` from the seeded
    Interpose ``ChallengeTemplate`` bound to each protected ally's character
    ObjectDB (``target_object``), so ``get_available_actions(interposer, room)``
    can surface the approach.

    - Specific-ally path (``focused_ally_target`` set): binds to that ally's character.
    - Any-ally path (``focused_ally_target=None``): binds to every ACTIVE participant
      in this encounter except the interposer, plus every ACTIVE ALLY-allegiance
      ``CombatOpponent``'s objectdb (a summon/companion NPC, #2207) — the only path
      that can bind a summon-ward, since ``focused_ally_target`` FKs
      ``CombatParticipant`` and so cannot name a specific opponent.

    Idempotent: ``get_or_create`` on (template, target_object, is_active=True) ensures
    no duplicates when called multiple times in the same round.

    No queries in loops: the active-ally list is fetched once per any-ally action;
    the template is fetched once before the loop.
    """
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    # Collect armed interpose actions for this round.
    interpose_actions = [
        action
        for action in pc_actions.values()
        if action.maneuver == CombatManeuver.INTERPOSE and action.is_ready
    ]
    if not interpose_actions:
        return

    try:
        template = ChallengeTemplate.objects.get(name="Interpose")
    except ChallengeTemplate.DoesNotExist:
        logger.warning(
            "Interpose ChallengeTemplate not seeded; skipping challenge binding for encounter %s.",
            encounter.pk,
        )
        return

    room = encounter.room

    # Fetch all active allies once (needed for the any-ally path).
    # select_related prevents N+1 when accessing .character_sheet.character below.
    active_participants_by_id: dict[int, CombatParticipant] | None = None
    # Fetch active ALLY-allegiance opponents (summons/companion NPCs) once too,
    # for the same any-ally path (#2207).
    active_ally_opponent_objectdbs: list[ObjectDB] | None = None

    for action in interpose_actions:
        interposer_participant_id = action.participant_id

        if action.focused_ally_target_id is not None:
            # Specific-ally path: bind to the declared ally's character.
            ally_char = action.focused_ally_target.character_sheet.character
            ChallengeInstance.objects.get_or_create(
                template=template,
                target_object=ally_char,
                is_active=True,
                defaults={"location": room, "is_revealed": True},
            )
        else:
            # Any-ally path: bind to every active participant except the interposer,
            # plus every active ALLY-allegiance opponent (summon/companion NPC, #2207).
            if active_participants_by_id is None:
                active_participants_by_id = {
                    p.pk: p
                    for p in CombatParticipant.objects.filter(
                        encounter=encounter,
                        status=ParticipantStatus.ACTIVE,
                    ).select_related("character_sheet__character")
                }
            if active_ally_opponent_objectdbs is None:
                active_ally_opponent_objectdbs = [
                    opp.objectdb
                    for opp in CombatOpponent.objects.filter(
                        encounter=encounter,
                        status=OpponentStatus.ACTIVE,
                        allegiance=CombatAllegiance.ALLY,
                    ).select_related("objectdb")
                    if opp.objectdb is not None
                ]
            _bind_interpose_challenges_any_ally(
                template,
                room,
                interposer_participant_id,
                active_participants_by_id,
                active_ally_opponent_objectdbs,
            )
