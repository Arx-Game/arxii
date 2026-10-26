"""Telegraphed windups: declaration, maturation, and riders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import (
    WINDUP_BLIND_DOWNGRADE,
    WINDUP_CALLED_OUT_DOWNGRADE,
    WINDUP_DOWNGRADE_STEP,
    WINDUP_FIZZLE_DOWNGRADES,
    WINDUP_MIN_DAMAGE_SCALE,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    PendingOpponentAttack,
    ThreatPoolEntry,
)
from world.combat.services.npc.area_attacks import place_of_participant
from world.combat.services.npc.npc_targeting import (
    _npc_action_target_pool,
    _select_opponent_targets,
    _select_targets,
    _set_npc_action_targets,
)
from world.combat.services.npc.windup_narration import (
    _broadcast_windup_fizzled,
    _broadcast_windup_telegraph,
    _broadcast_windup_wreck,
    _find_windup_caller,
)
from world.combat.types import ActionOutcome, OpponentDamageResult
from world.conditions.constants import Allegiance

if TYPE_CHECKING:
    from world.areas.positioning.models import Position


def _select_windup_targets(  # noqa: PLR0913
    entry: ThreatPoolEntry,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> list:
    """Same selection ``_set_npc_action_targets`` uses, minus the M2M write (#2637).

    A wind-up has no CombatOpponentAction row to attach an M2M to at
    declaration time — ``PendingOpponentAttack.target`` is a single nullable
    FK instead (v1 single-target). The caller collapses a one-element,
    participant-targeting selection into that FK; anything else (multi/ALL,
    or an opponent-targeting summon windup) stays room-targeting (``None``),
    re-derived at maturation.
    """
    if targeting_participants:
        return _select_targets(
            entry,
            target_pool,
            rotation=rotation,
            _threat_map=threat_map,
            _shield_participant_ids=shield_participant_ids,
        )
    # See _set_npc_action_targets: never forward the participant-keyed maps
    # into opponent-targeting selection (threat-map pk collision, #4091).
    return _select_opponent_targets(
        entry,
        target_pool,
        rotation=rotation,
        _threat_map=None,
        _shield_participant_ids=None,
    )


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

    Split out of ``plan_opponent_round`` to keep that function's
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
    covered = (
        place_of_participant(selected[0])
        if entry.covers_place and targeting_participants and selected
        else None
    )
    _create_pending_opponent_attack(opponent, entry, encounter, single_target, covered=covered)


def _create_pending_opponent_attack(
    opponent: CombatOpponent,
    entry: ThreatPoolEntry,
    encounter: CombatEncounter,
    target: CombatParticipant | None,
    *,
    covered: Position | None = None,
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
        covered_position=covered,
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

    # A place-covering wind-up lands on its place whoever stands there (#4676):
    # cover_place picks the occupants when it resolves.
    if pending.covered_position_id is not None:
        CombatOpponentAction.objects.create(
            opponent=pending.opponent,
            round_number=round_number,
            threat_entry=entry,
            damage_scale=scale,
            matured_from_called_out_windup=pending.called_out,
            covered_position=pending.covered_position,
        )
        pending.delete()
        return

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
