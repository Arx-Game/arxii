"""NPC attack declaration, windup and sustained maturation, sent-flying broadcasts."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from world.combat import services as _svc
from world.combat.constants import (
    SUSTAINED_HIT_DOWNGRADE,
    WINDUP_BLIND_DOWNGRADE,
    WINDUP_CALLED_OUT_DOWNGRADE,
    WINDUP_DOWNGRADE_STEP,
    WINDUP_FIZZLE_DOWNGRADES,
    WINDUP_MIN_DAMAGE_SCALE,
    OpponentStatus,
    ParticipantStatus,
    SustainedKind,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    CombatRoundActionTarget,
    PendingOpponentAttack,
    SustainedAction,
    ThreatPoolEntry,
)
from world.combat.services.declare_action import (
    _broadcast_sustained_broken,
    _broadcast_sustained_erosion,
    _broadcast_windup_fizzled,
    _broadcast_windup_telegraph,
    _broadcast_windup_wreck,
    _dual_dispatch_combat_narration,
    _find_windup_caller,
    _npc_action_target_pool,
    _select_windup_targets,
    _set_npc_action_targets,
)
from world.combat.types import ActionOutcome, OpponentDamageResult
from world.conditions.constants import Allegiance

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionTemplate


def _execute_npc_attack(  # noqa: PLR0913
    *,
    opponent: CombatOpponent,
    eligible: list[ThreatPoolEntry],
    encounter: CombatEncounter,
    target_pool: list,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None,
    shield_participant_ids: set[int] | None,
    actions: list[CombatOpponentAction],
) -> None:
    """Execute one NPC attack, appending to *actions* or declaring a windup.

    Picks a weighted-random threat entry; if it has ``windup_rounds > 0``
    declares a pending windup attack (no immediate row). Otherwise creates a
    ``CombatOpponentAction`` row and sets its targets.

    Args:
        opponent: The attacking ``CombatOpponent``.
        eligible: Eligible (off-cooldown) threat pool entries.
        encounter: The active ``CombatEncounter``.
        target_pool: The resolved target pool for this round.
        targeting_participants: Whether targeting uses participants.
        rotation: The attack index within the round (for rotation logic).
        threat_map: Optional threat-map for target selection.
        shield_participant_ids: Optional set of shield-bearing participant IDs.
        actions: The accumulator list to append created actions to.
    """
    weights = [e.weight for e in eligible]
    chosen = random.choices(eligible, weights=weights, k=1)[0]  # noqa: S311

    # Telegraphed wind-up (#2637 design 2-3): a windup_rounds entry commits
    # to a PendingOpponentAttack instead of a same-round CombatOpponentAction.
    # No CombatOpponentAction row exists for this attack until it matures.
    if chosen.windup_rounds > 0:
        _declare_windup_attack(
            opponent,
            chosen,
            encounter,
            target_pool,
            targeting_participants=targeting_participants,
            rotation=rotation,
            threat_map=threat_map,
            shield_participant_ids=shield_participant_ids,
        )
        return

    action = CombatOpponentAction.objects.create(
        opponent=opponent,
        round_number=encounter.round_number,
        threat_entry=chosen,
    )
    _set_npc_action_targets(
        action,
        chosen,
        target_pool,
        targeting_participants=targeting_participants,
        rotation=rotation,
        threat_map=threat_map,
        shield_participant_ids=shield_participant_ids,
    )
    actions.append(action)


# =============================================================================
# Telegraphed enemy wind-ups (#2637)
# =============================================================================


def _declare_windup_attack(  # noqa: PLR0913
    opponent: CombatOpponent,
    entry: ThreatPoolEntry,
    encounter: CombatEncounter,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> None:
    """Select this wind-up's target(s) and create its PendingOpponentAttack.

    Split out of ``_build_opponent_round_actions`` to keep that function's
    branch count within the lint threshold (#2637).
    """
    selected = _select_windup_targets(
        entry,
        target_pool,
        targeting_participants=targeting_participants,
        rotation=rotation,
        threat_map=threat_map,
        shield_participant_ids=shield_participant_ids,
    )
    single_target = selected[0] if targeting_participants and len(selected) == 1 else None
    _create_pending_opponent_attack(opponent, entry, encounter, single_target)


def _broadcast_sustained_held(sustained: SustainedAction) -> None:
    """Announce a PC sustained action holding through to maturation (#2705).

    No NPC-side analogue — a wind-up that matures resolves as an attack, which
    narrates through the normal NPC-attack broadcast path, not a dedicated
    "held" line. A held sustained action has no such downstream narration of
    its own (the cloned technique/dispatched ritual resolves silently into the
    normal PC pipeline), so this line is the only announcement it gets.
    """
    character_name = str(sustained.participant.character_sheet.character)
    narration = f"{character_name} completes {sustained.subject_name}!"
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)


def _create_pending_opponent_attack(
    opponent: CombatOpponent,
    entry: ThreatPoolEntry,
    encounter: CombatEncounter,
    target: CombatParticipant | None,
) -> PendingOpponentAttack:
    """Telegraph a wind-up instead of a same-round attack (#2637 design 2-3, 6).

    Resolves auto-callout (at most one call-out per round per encounter) and
    dual-dispatches the telegraph narration.
    """
    round_number = encounter.round_number
    already_called_out = PendingOpponentAttack.objects.filter(
        encounter=encounter,
        declared_round=round_number,
        called_out=True,
    ).exists()
    caller = None if already_called_out else _find_windup_caller(encounter)

    pending = PendingOpponentAttack.objects.create(
        encounter=encounter,
        opponent=opponent,
        threat_entry=entry,
        target=target,
        declared_round=round_number,
        resolves_round=round_number + entry.windup_rounds,
        called_out=caller is not None,
    )
    caller_name = str(caller.character_sheet.character) if caller is not None else None
    _broadcast_windup_telegraph(pending, caller_name=caller_name)
    return pending


def windup_damage_scale(downgrades: int) -> float:
    """The downgrade ladder: x(1 - 0.25*downgrades), floored at x0.25 (#2637 design 3)."""
    return max(WINDUP_MIN_DAMAGE_SCALE, 1.0 - WINDUP_DOWNGRADE_STEP * downgrades)


def _mature_one_pending_attack(
    encounter: CombatEncounter,
    pending: PendingOpponentAttack,
    round_number: int,
    *,
    allegiances: dict[int, Allegiance],
    active_opponents: list[CombatOpponent],
) -> None:
    """Resolve a single matured wind-up: fizzle, lose-target, or fire (#2637 design 3)."""
    from world.vitals.services import is_dead  # noqa: PLC0415

    if pending.downgrades >= WINDUP_FIZZLE_DOWNGRADES:
        _broadcast_windup_fizzled(pending)
        pending.delete()
        return

    if pending.opponent.status != OpponentStatus.ACTIVE:
        pending.delete()
        return

    entry = pending.threat_entry
    scale = windup_damage_scale(pending.downgrades)

    if pending.target_id is not None:
        target = pending.target
        if target.status != ParticipantStatus.ACTIVE or is_dead(target.character_sheet):
            _broadcast_windup_fizzled(pending, reason="loses its target")
            pending.delete()
            return
        action = CombatOpponentAction.objects.create(
            opponent=pending.opponent,
            round_number=round_number,
            threat_entry=entry,
            damage_scale=scale,
            matured_from_called_out_windup=pending.called_out,
        )
        action.targets.set([target])
        pending.delete()
        return

    # Room-targeting wind-up (no single stored target): re-derive the pool at
    # maturation the same way declaration did — participants may have fled,
    # died, or joined since the wind-up was telegraphed.
    active_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    target_pool, targeting_participants = _npc_action_target_pool(
        pending.opponent,
        active_participants,
        encounter,
        allegiances=allegiances,
        active_opponents=active_opponents,
    )
    if not target_pool:
        _broadcast_windup_fizzled(pending, reason="loses its target")
        pending.delete()
        return

    action = CombatOpponentAction.objects.create(
        opponent=pending.opponent,
        round_number=round_number,
        threat_entry=entry,
        damage_scale=scale,
        matured_from_called_out_windup=pending.called_out,
    )
    _set_npc_action_targets(
        action,
        entry,
        target_pool,
        targeting_participants=targeting_participants,
        rotation=0,
    )
    pending.delete()


def _mature_pending_opponent_attacks(encounter: CombatEncounter, round_number: int) -> None:
    """Mature every wind-up whose delay has elapsed this round (#2637 design 3, 5).

    Called from ``resolve_round`` after the encounter flips to RESOLVING but
    BEFORE the round's ``CombatOpponentAction`` rows are queried, so a matured
    wind-up's synthesized action is picked up by the normal NPC-resolution
    pipeline unmodified in the same pass.
    """
    pending_rows = list(
        PendingOpponentAttack.objects.filter(
            encounter=encounter,
            resolves_round=round_number,
        ).select_related("opponent", "threat_entry", "target__character_sheet__character")
    )
    if not pending_rows:
        return

    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    all_active = list(
        CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.ACTIVE)
    )
    allegiances = effective_allegiances(all_active)
    for pending in pending_rows:
        _mature_one_pending_attack(
            encounter,
            pending,
            round_number,
            allegiances=allegiances,
            active_opponents=all_active,
        )


def _mature_sustained_technique(sustained: SustainedAction, round_number: int) -> None:
    """Clone the declaring ``CombatRoundAction`` into the maturation round (#2705).

    ``declared_action`` is null only in a data-integrity gap — it must always be
    set at TECHNIQUE declaration time (see ``_sync_sustained_technique_declaration``)
    — treated as a broken commitment rather than silently dropped.

    Resets the per-round/resolution fields that would otherwise carry stale state
    forward from the DECLARING round: ``is_ready`` (flips True so the matured
    action behaves like a normal ready declaration), ``interaction`` /
    ``interaction_timestamp`` (the ACTION-mode Interaction, if any, belongs to
    the declaring round's resolution — a stale FK here would misattribute this
    round's narration to that one), ``combo_upgrade`` (a combo detected against
    the DECLARING round's board has no bearing on the maturation round's board),
    ``succor_resolution`` (a cached Succor outcome is round-scoped), ``from_
    entrance`` (a windup declared as a dramatic technique entrance must not
    spuriously re-fire ``_maybe_suggest_entrance_dramatic_moment`` N rounds
    later — ``_resolve_pc_action`` fires that suggestion whenever
    ``action.from_entrance`` is true, #2705 adversarial review, Fix 4), and
    ``maneuver`` / ``item_instance`` (a maneuver and the item it uses belong to
    the DECLARING round's action shape — a sustained commitment is never itself
    a maneuver — not to the matured cast).

    **Deliberately PRESERVED, not reset:** ``confirm_soulfray_risk`` (the
    player's consent for THIS specific cast — it does not expire at maturation,
    it IS what the player is committing to) and the cast geometry FKs
    (``cast_destination``, ``cast_position_a``, ``cast_position_b``,
    ``redirect_opponent_target``, ``redirect_object_target``) — these describe
    the declared cast itself, not per-round resolution bookkeeping, so they
    carry forward unchanged into the maturation round.

    Does **not** delete a pre-existing same-round row to make room: decision D2
    (enforced by ``_validate_no_pending_sustained``) means one cannot exist while
    this commitment is pending — an ``IntegrityError`` here would mean D2's
    invariant broke elsewhere, and surfacing that beats silently discarding a
    player's declaration.

    **Deliberate deviation from the plan's literal ``clone.pk = None`` recipe**
    (verified with a scratch repro during implementation — a real bug, not a
    style preference): ``CombatRoundAction`` is a ``SharedMemoryModel``
    (idmapper identity map). Nulling ``pk``/``id`` on the fetched ``original``
    instance and re-``save()``-ing it reassigns a NEW pk to that SAME cached
    Python object, but the idmapper's cache entry for the ORIGINAL pk is never
    updated — it keeps pointing at this now-mutated object. Any later
    ``CombatRoundAction.objects.get(pk=<declaring round's pk>)`` in the same
    process (audit views, admin, a future round's queries) would silently
    return the MATURATION round's data instead of the true declaring-round
    row, for the remaining life of the process. Building a plain field dict
    and calling ``.objects.create()`` instead sidesteps this entirely — the
    fetched ``original`` instance and its cache entry are never touched, and a
    genuinely new instance/row is created for the new pk. The field dict is
    built from ``original._meta.concrete_fields`` rather than a hardcoded
    list so a future field addition to ``CombatRoundAction`` is copied
    automatically instead of silently dropped.
    """
    if sustained.declared_action_id is None:
        _broadcast_sustained_broken(sustained, reason="comes to nothing")
        sustained.delete()
        return

    original = sustained.declared_action
    extra_target_opponent_ids = list(original.extra_targets.values_list("opponent_id", flat=True))

    fields = {
        field.attname: getattr(original, field.attname)
        for field in original._meta.concrete_fields  # noqa: SLF001
        if not field.primary_key
    }
    fields["round_number"] = round_number
    fields["is_ready"] = True
    fields["interaction_id"] = None
    fields["interaction_timestamp"] = None
    fields["combo_upgrade_id"] = None
    fields["succor_resolution"] = None
    fields["from_entrance"] = False
    fields["maneuver"] = None
    fields["item_instance_id"] = None
    clone = CombatRoundAction.objects.create(**fields)

    if extra_target_opponent_ids:
        CombatRoundActionTarget.objects.bulk_create(
            [
                CombatRoundActionTarget(action=clone, opponent_id=opponent_id)
                for opponent_id in extra_target_opponent_ids
            ]
        )

    _broadcast_sustained_held(sustained)
    sustained.delete()


def _mature_sustained_ritual(sustained: SustainedAction) -> None:
    """Dispatch the held ritual at maturation, or break on a content-surface error (#2705).

    The RITUAL sibling of ``_mature_sustained_technique``. Components were
    already validated and consumed at declaration
    (``PerformRitualAction._validate_components``, before
    ``try_declare_sustained_ritual`` ever creates this row) — so a caught
    failure here still deletes the row with no refund, the same "the cost
    stands" ruling ``_mature_one_sustained_action`` applies to the
    downgrades-exceeded break one level up.

    Catches only the same ritual-surface exceptions ``PerformRitualAction``
    itself catches (``RitualComponentError`` / ``ResonanceInsufficient`` /
    ``AnchorCapExceeded`` / ``InvalidImbueAmount`` / ``XPInsufficient`` /
    ``GhostTutorError``) — a content-authoring gap in ONE participant's
    ritual must not abort round resolution for every other combatant.
    Deliberately does NOT catch bare ``Exception`` (no defensive
    error-papering, CLAUDE.md) — an unexpected crash here should surface
    loudly, not be swallowed into a generic broken-ritual line.
    """
    from world.magic.exceptions import (  # noqa: PLC0415
        AnchorCapExceeded,
        GhostTutorError,
        InvalidImbueAmount,
        ResonanceInsufficient,
        RitualComponentError,
        XPInsufficient,
    )
    from world.magic.services.ritual_dispatch import dispatch_ritual  # noqa: PLC0415

    try:
        dispatch_ritual(
            ritual=sustained.ritual,
            performer_sheet=sustained.participant.character_sheet,
        )
    except (
        RitualComponentError,
        ResonanceInsufficient,
        AnchorCapExceeded,
        InvalidImbueAmount,
        XPInsufficient,
        GhostTutorError,
    ):
        _broadcast_sustained_broken(sustained, reason="fizzles")
        sustained.delete()
        return

    _broadcast_sustained_held(sustained)
    sustained.delete()


def _mature_one_sustained_action(sustained: SustainedAction, round_number: int) -> None:
    """Resolve a single matured ``SustainedAction``: break, lose-holder, or hold (#2705).

    Mirrors ``_mature_one_pending_attack``'s three-way branch shape. Unlike the
    NPC side there is no damage ramp (D1, ADR-0188) — a held commitment resolves
    at full effect or not at all.

    1. ``downgrades > 0 and downgrades >= absorption_budget`` -> broken. **The
       cost stands — nothing is refunded.** Components/anima were charged at
       declaration (rituals, Task 5); the spec's ruling is that a broken
       sustain is simply spent, which is what makes committing to one real
       stakes rather than a free retry. Requires ``downgrades > 0``, not just
       ``>=``, so that a Critical-Failure budget of 0 breaks on the participant's
       FIRST LANDING HIT (``_apply_sustained_erosion_rider`` takes it to
       ``downgrades=1``, already ``>= 0``) rather than at maturation regardless
       of whether the participant was ever touched — ``0 >= 0`` alone would
       fizzle an untouched commitment in total safety, which the approved spec
       never intended (#2705 adversarial review, Fix 5).
    2. The holder can no longer hold it together (left the encounter or died) ->
       broken, distinct "comes to nothing" narration.
    3. ``SustainedKind.TECHNIQUE`` -> clone the declaring action into this round.
    4. ``SustainedKind.RITUAL`` -> dispatch the ritual's authored execution
       payload (Task 5's ``_mature_sustained_ritual``); a caught content-surface
       exception breaks the commitment instead of raising through round
       resolution.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    if sustained.downgrades > 0 and sustained.downgrades >= sustained.absorption_budget:
        _broadcast_sustained_broken(sustained)
        sustained.delete()
        return

    participant = sustained.participant
    if participant.status != ParticipantStatus.ACTIVE or is_dead(participant.character_sheet):
        _broadcast_sustained_broken(sustained, reason="comes to nothing")
        sustained.delete()
        return

    if sustained.sustained_kind == SustainedKind.TECHNIQUE:
        _mature_sustained_technique(sustained, round_number)
        return

    _mature_sustained_ritual(sustained)


def _mature_sustained_actions(encounter: CombatEncounter, round_number: int) -> None:
    """Mature every PC ``SustainedAction`` whose commitment resolves this round (#2705).

    The PC-side sibling of ``_mature_pending_opponent_attacks`` — called from
    ``resolve_round`` immediately after it, in the same pass, BEFORE the
    round's ``CombatRoundAction`` rows are queried into ``pc_actions``, so a
    held technique's cloned row is picked up by the normal PC pipeline
    unmodified in the same pass.
    """
    rows = list(
        SustainedAction.objects.filter(
            encounter=encounter,
            resolves_round=round_number,
        ).select_related(
            "participant__character_sheet__character",
            "ritual",
            "technique",
            "declared_action",
        )
    )
    for sustained in rows:
        _mature_one_sustained_action(sustained, round_number)


def _apply_windup_interception_rider(
    target: CombatOpponent,
    outcome: ActionOutcome,
    attacker_participant: CombatParticipant,
) -> None:
    """A landing PC hit on a winding-up opponent adds downgrades (#2637 design 4).

    Only fires on hits that dealt damage > 0 against ``target``. +1 downgrade
    blind, +2 when the wind-up is ``called_out`` (called-out beats blind).
    Only matches a NOT-YET-MATURED pending row (``resolves_round >=`` the
    current round) — a wind-up maturing THIS round is already resolved and
    deleted before PC actions resolve, so this can only ever reach a future
    one.
    """
    landed = any(
        isinstance(damage_result, OpponentDamageResult)
        and damage_result.opponent_id == target.pk
        and damage_result.damage_dealt > 0
        for damage_result in outcome.damage_results
    )
    if not landed:
        return

    pending = PendingOpponentAttack.objects.filter(
        opponent=target,
        resolves_round__gte=target.encounter.round_number,
    ).first()
    if pending is None:
        return

    increment = WINDUP_CALLED_OUT_DOWNGRADE if pending.called_out else WINDUP_BLIND_DOWNGRADE
    pending.downgrades += increment
    pending.save(update_fields=["downgrades"])
    _broadcast_windup_wreck(pending, str(attacker_participant.character_sheet.character))


def _apply_sustained_erosion_rider(participant: CombatParticipant, damage_dealt: int) -> None:
    """A landing hit on a sustaining PC adds a downgrade to their commitment (#2705).

    The PC-side sibling of ``_apply_windup_interception_rider``. Only fires on
    ``damage_dealt > 0`` — a fully-mitigated hit does not erode anything.
    Matches a NOT-YET-MATURED row (``resolves_round__gte`` the current round)
    for the same reason the windup rider does: a ``SustainedAction`` maturing
    THIS round is already resolved and deleted by ``_mature_sustained_actions``
    before PC damage resolves this round, so this can only ever reach a future
    one.

    Unlike the NPC side there is no ``called_out``/blind split: a PC's
    sustained action is telegraphed publicly the moment it is declared (see
    ``_broadcast_sustained_telegraph``), so there is nothing to "call out" —
    every landing hit erodes by the same flat ``SUSTAINED_HIT_DOWNGRADE``.
    """
    if damage_dealt <= 0:
        return

    sustained = SustainedAction.objects.filter(
        participant=participant,
        resolves_round__gte=participant.encounter.round_number,
    ).first()
    if sustained is None:
        return

    sustained.downgrades += SUSTAINED_HIT_DOWNGRADE
    sustained.save(update_fields=["downgrades"])
    _broadcast_sustained_erosion(sustained)


# ---------------------------------------------------------------------------
# Sent Flying (#2638) — the plummet-pattern's first "in-flight" consequence.
#
# A sends_flying ThreatPoolEntry's attack that lands damage > 0 applies the
# seeded "Sent Flying" marker condition (a produced, reactable moment — see
# world.combat.sent_flying_content) and is IMMEDIATELY answerable by the same
# armed-INTERPOSE reaction economy _try_interpose reads. Left unanswered, the
# marker resolves explicitly at the end of resolve_round: a plummet if the
# victim's room supports one, else a hard-landing impact debit.
# ---------------------------------------------------------------------------


def _broadcast_sent_flying_launch(participant: CombatParticipant) -> None:
    """Announce a Sent Flying marker landing (#2638) — the produced moment."""
    name = str(participant.character_sheet.character)
    narration = f"{name} is sent FLYING by the blow!"
    _dual_dispatch_combat_narration(participant.encounter, narration)


def _sent_flying_windup_caller(
    encounter: CombatEncounter, npc_action: CombatOpponentAction
) -> str | None:
    """The wind-up caller's name if *npc_action* matured from a called-out wind-up.

    ``PendingOpponentAttack`` (which carries ``called_out``) is deleted at
    maturation, so ``matured_from_called_out_windup`` is the only surviving
    record. v1 approximation: re-derives the CURRENT flagged auto-caller via
    ``_find_windup_caller`` rather than persisting the specific caller who
    called THIS wind-up out — at most one call-out fires per round per
    encounter (#2637 design 6), so this is accurate whenever the flagged role
    hasn't changed hands mid-round, which is the overwhelmingly common case.
    """
    if not npc_action.matured_from_called_out_windup:
        return None
    caller = _find_windup_caller(encounter)
    return str(caller.character_sheet.character) if caller is not None else None


def _broadcast_sent_flying_catch(
    participant: CombatParticipant,
    npc_action: CombatOpponentAction,
    catcher: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Announce a mid-air catch (#2638), naming the catcher + the caller if any."""
    victim_name = str(participant.character_sheet.character)
    narration = f"{catcher} catches {victim_name} out of the air!"
    caller_name = _sent_flying_windup_caller(participant.encounter, npc_action)
    if caller_name:
        narration = f"{narration} {caller_name}'s call-out made the difference!"
    _dual_dispatch_combat_narration(participant.encounter, narration)


def _clear_sent_flying_marker(
    participant: CombatParticipant,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    template: ConditionTemplate,
) -> None:
    """Remove the Sent Flying condition + reset its damage carrier (#2638)."""
    from world.conditions.services import remove_condition  # noqa: PLC0415

    remove_condition(character, template)
    participant.sent_flying_damage = 0
    participant.save(update_fields=["sent_flying_damage"])


def swarm_kills(raw_damage: int, body_toughness: int) -> int:
    """Bodies a single landing attack clears from a swarm (#875).

    A landing hit always clears at least one body; big hits mow through many.
    ``body_toughness`` is the damage needed per body.
    """
    if raw_damage <= 0:
        return 0
    return max(1, raw_damage // max(1, body_toughness))


def swarm_attack_count(swarm_count: int, bodies_per_attack: int, active_pc_count: int) -> int:
    """Attacks a swarm makes this round — scales with remaining bodies (#875).

    Capped at the number of PCs who can act, so a swarm fans across the party
    rather than dogpiling one PC. Derived on read; nothing persisted.
    """
    if swarm_count <= 0 or active_pc_count <= 0:
        return 0
    raw = math.ceil(swarm_count / max(1, bodies_per_attack))
    return max(1, min(raw, active_pc_count))
