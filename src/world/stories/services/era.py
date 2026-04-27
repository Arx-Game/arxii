"""Era lifecycle service functions.

advance_era(next_era) closes the current ACTIVE era and activates the
provided UPCOMING era atomically. archive_era(era) marks an active or
concluded era as CONCLUDED. Stories continue across eras — no
auto-mutation of in-flight stories.
"""

from django.db import transaction
from django.utils import timezone

from world.stories.constants import EraStatus
from world.stories.exceptions import EraAdvanceError
from world.stories.models import Era


def advance_era(*, next_era: Era) -> Era:
    """Close the current ACTIVE era; activate the given UPCOMING era.

    Stories continue across eras (per Phase 1 design); no automatic
    mutation of in-flight stories occurs.

    Raises EraAdvanceError if next_era is not UPCOMING.
    """
    if next_era.status != EraStatus.UPCOMING:
        msg = "Next era must be in UPCOMING status to advance."
        raise EraAdvanceError(msg)
    now = timezone.now()
    with transaction.atomic():
        # Close any current ACTIVE era — use save() (not bulk update) so that
        # SharedMemoryModel's in-memory identity map stays coherent.
        current_active = Era.objects.filter(status=EraStatus.ACTIVE).first()
        if current_active is not None:
            current_active.status = EraStatus.CONCLUDED
            current_active.concluded_at = now
            current_active.save(update_fields=["status", "concluded_at"])
        next_era.status = EraStatus.ACTIVE
        next_era.activated_at = now
        next_era.save(update_fields=["status", "activated_at"])
    return next_era


def archive_era(*, era: Era) -> Era:
    """Mark an era CONCLUDED without advancing to a new one.

    Idempotent for already-CONCLUDED eras. Raises EraAdvanceError
    if era is UPCOMING (use advance_era to retire an UPCOMING era — but
    that's an unusual workflow; prefer creating + activating + then
    archiving; or just deleting).
    """
    if era.status == EraStatus.UPCOMING:
        msg = "Cannot archive an UPCOMING era. Activate via advance_era first, or delete."
        raise EraAdvanceError(msg)
    if era.status == EraStatus.ACTIVE:
        era.status = EraStatus.CONCLUDED
        era.concluded_at = timezone.now()
        era.save(update_fields=["status", "concluded_at"])
    return era
