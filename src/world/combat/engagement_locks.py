"""Service functions for engagement locks — foil duel pairings (#2020).

Lock formation (autonomous threat threshold, PC challenge, GM declared) and
breaking (defeat, flee, disengage). Flow events emitted on formation/breaking
so triggers can narrate dramatic beats.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import (
    EngagementLockStatus,
    LockInitiator,
    SurgeTriggerKind,
)
from world.combat.models import (
    CombatOpponent,
    CombatParticipant,
    EngagementLock,
    ThreatRecord,
)

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter


def create_engagement_lock(
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    participant: CombatParticipant,
    *,
    initiated_by: str = LockInitiator.THREAT,
) -> EngagementLock:
    """Create an ACTIVE EngagementLock + emit ENGAGEMENT_LOCK_FORMED.

    No-op (returns existing lock) if an active lock already exists for this
    opponent.

    Args:
        encounter: The combat encounter.
        opponent: The NPC opponent being locked.
        participant: The PC participant being locked to.
        initiated_by: How the lock was formed (threat/PC/GM).

    Returns:
        The existing or newly-created ``EngagementLock``.
    """
    lock, created = EngagementLock.objects.get_or_create(
        encounter=encounter,
        opponent=opponent,
        status=EngagementLockStatus.ACTIVE,
        defaults={
            "participant": participant,
            "initiated_by": initiated_by,
            "started_round": encounter.round_number,
        },
    )
    if not created:
        return lock

    _emit_lock_formed(encounter, lock)
    return lock


def break_engagement_lock(
    lock: EngagementLock,
    *,
    reason: str,
) -> None:
    """Break an active EngagementLock + emit ENGAGEMENT_LOCK_BROKEN.

    No-op if the lock is not ACTIVE.

    Args:
        lock: The engagement lock to break.
        reason: Why the lock ended (LockBreakReason).
    """
    if lock.status != EngagementLockStatus.ACTIVE:
        return

    lock.status = EngagementLockStatus.BROKEN
    lock.break_reason = reason
    lock.ended_round = lock.encounter.round_number
    lock.save(update_fields=["status", "break_reason", "ended_round"])

    _emit_lock_broken(lock)


def check_auto_lock_formation(encounter: CombatEncounter) -> None:
    """Check all opponents for threat-threshold crossing -> autonomous lock (#2020).

    Called at the start of ``select_npc_actions`` (before NPC targeting). For
    each opponent with no active lock, finds the ThreatRecord with the highest
    threat_value; if it crosses ``opponent.auto_lock_threshold``, creates a
    lock with ``initiated_by=THREAT``.

    Args:
        encounter: The combat encounter to check.
    """
    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status="active",
        ).exclude(threat_pool__isnull=True)
    )
    if not opponents:
        return

    # Skip opponents that already have an active lock.
    locked_opponent_ids = set(
        EngagementLock.objects.filter(
            encounter=encounter,
            status=EngagementLockStatus.ACTIVE,
        ).values_list("opponent_id", flat=True)
    )

    for opponent in opponents:
        if opponent.pk in locked_opponent_ids:
            continue

        top_threat = (
            ThreatRecord.objects.filter(
                encounter=encounter,
                opponent=opponent,
            )
            .select_related("participant")
            .order_by("-threat_value")
            .first()
        )
        if top_threat is None or top_threat.threat_value < opponent.auto_lock_threshold:
            continue

        create_engagement_lock(
            encounter,
            opponent,
            top_threat.participant,
            initiated_by=LockInitiator.THREAT,
        )
        locked_opponent_ids.add(opponent.pk)


def create_engagement_lock_for_challenge(
    participant: CombatParticipant,
    opponent_id: int,
) -> None:
    """PC-initiated lock: spike threat to force threshold crossing (#2020).

    Raises ValueError if the opponent is not in the same encounter or is
    already locked to a different PC.

    Args:
        participant: The PC participant challenging.
        opponent_id: The pk of the NPC opponent to engage.

    Raises:
        ValueError: If the opponent doesn't exist, isn't in the encounter, or
            is already locked to a different PC.
    """
    from world.combat.models import CombatOpponent  # noqa: PLC0415
    from world.combat.services import accumulate_threat  # noqa: PLC0415

    encounter = participant.encounter
    try:
        opponent = CombatOpponent.objects.get(pk=opponent_id, encounter=encounter)
    except CombatOpponent.DoesNotExist:
        msg = "That opponent is not in your encounter."
        raise ValueError(msg) from None

    # Check for existing active lock on a different PC.
    existing = EngagementLock.objects.filter(
        opponent=opponent,
        status=EngagementLockStatus.ACTIVE,
    ).first()
    if existing is not None and existing.participant_id != participant.pk:
        msg = "That opponent is already engaged in a duel with someone else."
        raise ValueError(msg)

    # Spike threat to threshold + 1 — guarantees lock formation next pass.
    accumulate_threat(encounter, opponent, participant, opponent.auto_lock_threshold + 1)


def trigger_interference_drama(
    lock: EngagementLock,
    interloper: CombatParticipant,
) -> None:
    """Fire the narrative payoff when a non-locked PC attacks a locked opponent (#2020).

    This is a *dramatic beat*, not a penalty: the interloper's attack still
    resolves normally. The payoff is:

    1. The break_in_consequence_pool fires (if set) — GM-authored dramatic effects.
    2. A SurgeTriggerKind.INTERFERENCE dramatic surge fires for the locked
       duelist (if the encounter has an EscalationCurve with
       interference_spike_intensity_amount > 0).

    The interference does NOT auto-break the lock.

    Args:
        lock: The active engagement lock being interfered with.
        interloper: The PC participant who is interfering.
    """
    from world.combat.escalation import apply_dramatic_surge  # noqa: PLC0415

    encounter = lock.encounter

    # Fire the consequence pool (GM-authored dramatic effects).
    if lock.break_in_consequence_pool_id is not None:
        from world.checks.consequence_resolution import (  # noqa: PLC0415
            apply_pool_deterministically,
        )
        from world.checks.types import ResolutionContext  # noqa: PLC0415

        context = ResolutionContext(
            character=lock.participant.character_sheet.character,
        )
        apply_pool_deterministically(
            pool=lock.break_in_consequence_pool,
            context=context,
        )

    # Fire the interference surge for the locked duelist (if curve exists).
    curve = encounter.escalation_curve
    if curve is not None and curve.interference_spike_intensity_amount > 0:
        apply_dramatic_surge(
            encounter=encounter,
            participant=lock.participant,
            amount=curve.interference_spike_intensity_amount,
            trigger_kind=SurgeTriggerKind.INTERFERENCE,
            subject_sheet=interloper.character_sheet,
        )


def _emit_lock_formed(encounter: CombatEncounter, lock: EngagementLock) -> None:
    """Emit ENGAGEMENT_LOCK_FORMED flow event for narration triggers."""
    from flows.constants import EventName  # noqa: PLC0415
    from flows.emit import emit_event  # noqa: PLC0415

    room = encounter.room
    if room is None:
        return
    emit_event(
        EventName.ENGAGEMENT_LOCK_FORMED,
        {
            "lock_id": lock.pk,
            "opponent_id": lock.opponent_id,
            "participant_id": lock.participant_id,
        },
        location=room,
    )


def _emit_lock_broken(lock: EngagementLock) -> None:
    """Emit ENGAGEMENT_LOCK_BROKEN flow event for narration triggers."""
    from flows.constants import EventName  # noqa: PLC0415
    from flows.emit import emit_event  # noqa: PLC0415

    room = lock.encounter.room
    if room is None:
        return
    emit_event(
        EventName.ENGAGEMENT_LOCK_BROKEN,
        {
            "lock_id": lock.pk,
            "opponent_id": lock.opponent_id,
            "participant_id": lock.participant_id,
            "break_reason": lock.break_reason,
        },
        location=room,
    )
