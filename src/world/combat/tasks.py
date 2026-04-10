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
    resolves each one individually. Each encounter is locked and
    resolved in its own transaction to prevent one failure from
    blocking others.

    Returns list of resolved encounter IDs.
    """
    now = timezone.now()

    # Find candidates without locking
    candidate_ids = list(
        CombatEncounter.objects.filter(
            status=EncounterStatus.DECLARING,
            pace_mode=PaceMode.TIMED,
            is_paused=False,
            round_started_at__isnull=False,
        ).values_list("pk", flat=True)
    )

    resolved_ids: list[int] = []
    for enc_id in candidate_ids:
        try:
            with transaction.atomic():
                enc = CombatEncounter.objects.select_for_update().get(
                    pk=enc_id,
                    status=EncounterStatus.DECLARING,  # Re-check under lock
                )
                deadline = enc.round_started_at + timedelta(
                    minutes=enc.pace_timer_minutes,
                )
                if now >= deadline:
                    from world.combat.services import resolve_round  # noqa: PLC0415

                    resolve_round(enc)
                    resolved_ids.append(enc_id)
                    logger.info(
                        "Auto-resolved timed encounter %d (round %d)",
                        enc.pk,
                        enc.round_number,
                    )
        except CombatEncounter.DoesNotExist:
            pass  # Already resolved by GM or status changed
        except Exception:
            logger.exception("Failed to auto-resolve encounter %d", enc_id)

    return resolved_ids
