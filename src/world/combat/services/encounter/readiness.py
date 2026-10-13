"""Toggling a participant's ready state and resolving on ready."""

from __future__ import annotations

from world.combat.constants import PaceMode, ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
from world.combat.services.rounds.resolution import resolve_round
from world.combat.types import RoundResolutionResult
from world.scenes.constants import RoundStatus


def toggle_action_ready(action: CombatRoundAction) -> CombatRoundAction:
    """Flip the ready flag on a round action and persist it.

    Extracted from the inline toggle that lived in the web ``ready`` endpoint so
    both the telnet/web shared ``ReadyAction`` and any caller use one code path.
    """
    action.is_ready = not action.is_ready
    action.save(update_fields=["is_ready"])
    return action


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
