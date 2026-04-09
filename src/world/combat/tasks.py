"""Combat timer task for auto-resolving timed rounds."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db import transaction
from django.utils import timezone

from world.combat.constants import EncounterStatus, PaceMode
from world.combat.models import CombatEncounter

logger = logging.getLogger(__name__)


def check_and_resolve_timed_encounters() -> list[int]:
    """Find expired timed encounters and auto-resolve them.

    Called periodically by the game clock scheduler. Queries for
    DECLARING encounters in TIMED mode past their deadline, then
    resolves each one. Uses select_for_update to prevent double
    resolution from concurrent runs.

    Returns list of resolved encounter IDs.
    """
    now = timezone.now()
    resolved_ids: list[int] = []

    with transaction.atomic():
        expired = list(
            CombatEncounter.objects.select_for_update().filter(
                status=EncounterStatus.DECLARING,
                pace_mode=PaceMode.TIMED,
                is_paused=False,
                round_started_at__isnull=False,
            )
        )

        for encounter in expired:
            deadline = encounter.round_started_at + timedelta(
                minutes=encounter.pace_timer_minutes,
            )
            if now >= deadline:
                try:
                    from world.combat.services import resolve_round  # noqa: PLC0415

                    resolve_round(encounter)
                    resolved_ids.append(encounter.pk)
                    logger.info(
                        "Auto-resolved timed encounter %d (round %d)",
                        encounter.pk,
                        encounter.round_number,
                    )
                except Exception:
                    logger.exception(
                        "Failed to auto-resolve encounter %d",
                        encounter.pk,
                    )

    return resolved_ids
