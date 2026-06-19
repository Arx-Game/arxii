"""Service: time-based cleanup of soft-deleted, non-lore-critical items (#1025)."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.utils import timezone

from world.items.constants import PROVENANCE_EVENT_TYPES
from world.items.models import ItemInstance
from world.items.services.usage import hard_delete_item_instance

logger = logging.getLogger(__name__)


def purge_expired_soft_deleted_items(*, grace: timedelta | None = None) -> int:
    """Hard-delete soft-deleted ItemInstance rows that are past the grace
    period AND not lore-critical (no facets, no transfer provenance, no
    ``lore_value``). Deletes each row's whole footprint via
    ``hard_delete_item_instance`` (no dangling FKs). Returns the count purged.

    ``grace`` defaults to ``settings.ITEM_SOFT_DELETE_GRACE_DAYS`` days.

    A soft-deleted item must never be in the game world. Any otherwise-eligible
    instance whose ``game_object`` still has a location (e.g. a half-undelete
    that moved the object back into play but left ``destroyed_at`` set) is NOT
    purged — it is logged for staff to resolve (clear ``destroyed_at`` to truly
    undelete it, or pull it back out of the world).

    PROTECT-referenced instances (those with a Mantle or ProjectContribution
    FK) are excluded from the eligibility queryset. Additionally, each deletion
    runs in its own savepoint so that any unexpected ProtectedError from a
    future FK addition skips that row instead of aborting the whole batch."""
    if grace is None:
        grace = timedelta(days=settings.ITEM_SOFT_DELETE_GRACE_DAYS)
    cutoff = timezone.now() - grace

    eligible = list(
        ItemInstance.objects.filter(destroyed_at__lt=cutoff, lore_value=0)
        .filter(mantle__isnull=True, project_contributions__isnull=True)
        .select_related("game_object")
        .annotate(
            facet_count=Count("item_facets", distinct=True),
            transfer_count=Count(
                "ownership_events",
                filter=Q(ownership_events__event_type__in=PROVENANCE_EVENT_TYPES),
                distinct=True,
            ),
        )
        .filter(facet_count=0, transfer_count=0)
    )

    # Safety guard: a soft-deleted item must not be in the game world. If its
    # game_object has a location, someone re-homed it without clearing
    # destroyed_at (a half-undelete) — never purge it; surface it instead.
    in_world = []
    purgeable = []
    for instance in eligible:
        if instance.game_object_id is not None and instance.game_object.db_location_id is not None:
            in_world.append(instance)
        else:
            purgeable.append(instance)
    if in_world:
        logger.warning(
            "purge_expired_soft_deleted_items: %d soft-deleted item(s) are in the game "
            "world while flagged for deletion (pks=%s); NOT purging. Resolve by clearing "
            "destroyed_at to undelete, or removing them from the world.",
            len(in_world),
            [instance.pk for instance in in_world],
        )

    purged = 0
    for instance in purgeable:
        try:
            with transaction.atomic():
                hard_delete_item_instance(instance)
            purged += 1
        except ProtectedError:
            logger.warning(
                "purge_expired_soft_deleted_items: skipping ItemInstance pk=%s — "
                "ProtectedError (PROTECT FK still references this row); "
                "exclude it from the eligibility filter to suppress this warning.",
                instance.pk,
            )
    return purged
