"""Engagement locks: breaking on defeat and interference."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import EngagementLockStatus
from world.combat.models import CombatOpponent, CombatParticipant, EngagementLock

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def _break_engagement_lock_on_defeat(
    opponent: CombatOpponent, *, reason: str | None = None
) -> None:
    """Release the opponent's active engagement lock, if any, on its defeat (#2020).

    ``reason`` defaults to ``LockBreakReason.DEFEAT`` (the original call site);
    ``remove_opponent`` (#3382) passes ``LockBreakReason.REMOVED`` for a GM pull,
    reusing this same lock-breaking seam rather than duplicating the query.
    """
    from world.combat.constants import LockBreakReason  # noqa: PLC0415
    from world.combat.engagement_locks import break_engagement_lock  # noqa: PLC0415

    active_lock = EngagementLock.objects.filter(
        opponent=opponent,
        status=EngagementLockStatus.ACTIVE,
    ).first()
    if active_lock is not None:
        break_engagement_lock(active_lock, reason=reason or LockBreakReason.DEFEAT)


def _maybe_trigger_lock_interference(
    opponent: CombatOpponent, source_sheet: CharacterSheet
) -> None:
    """Fire the duel-interference beat when a non-locked PC hits a locked opponent (#3447).

    The narrative payoff #2020 designed but never called: the locked duelist's
    ``break_in_consequence_pool`` fires and an INTERFERENCE dramatic surge lands
    on them (see :func:`world.combat.engagement_locks.trigger_interference_drama`).
    Dedup rides the surge's own ``DramaticSurgeRecord`` trail — checked here (not
    only inside ``apply_dramatic_surge``) so once the surge has fired, the
    consequence-pool leg cannot repeat on later hits: at most one full beat per
    (locked duelist, interloper) per encounter. A record only exists when the
    encounter's escalation curve actually surged, so a lock authored with a
    ``break_in_consequence_pool`` on a curve-less encounter refires the pool per
    landing hit — author such pools one-shot-safe, or give the encounter a curve.
    """
    from world.combat.constants import SurgeTriggerKind  # noqa: PLC0415
    from world.combat.engagement_locks import trigger_interference_drama  # noqa: PLC0415
    from world.combat.models import DramaticSurgeRecord  # noqa: PLC0415

    active_lock = (
        EngagementLock.objects.filter(
            opponent=opponent,
            status=EngagementLockStatus.ACTIVE,
        )
        .select_related("participant")
        .first()
    )
    if active_lock is None or active_lock.participant.character_sheet_id == source_sheet.pk:
        return

    interloper = CombatParticipant.objects.filter(
        encounter=opponent.encounter,
        character_sheet=source_sheet,
    ).first()
    if interloper is None:
        return

    already_fired = DramaticSurgeRecord.objects.filter(
        encounter=opponent.encounter,
        participant=active_lock.participant,
        trigger_kind=SurgeTriggerKind.INTERFERENCE,
        subject_sheet=source_sheet,
    ).exists()
    if already_fired:
        return

    trigger_interference_drama(active_lock, interloper)
