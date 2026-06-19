"""Service: time-based cleanup of soft-deleted, non-lore-critical items (#1025)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from world.items.constants import PROVENANCE_EVENT_TYPES
from world.items.models import ItemInstance
from world.items.services.usage import hard_delete_item_instance


@transaction.atomic
def purge_expired_soft_deleted_items(*, grace: timedelta | None = None) -> int:
    """Hard-delete soft-deleted ItemInstance rows that are past the grace
    period AND not lore-critical (no facets, no transfer provenance, no
    ``lore_value``). Deletes each row's whole footprint via
    ``hard_delete_item_instance`` (no dangling FKs). Returns the count purged.

    ``grace`` defaults to ``settings.ITEM_SOFT_DELETE_GRACE_DAYS`` days."""
    if grace is None:
        grace = timedelta(days=settings.ITEM_SOFT_DELETE_GRACE_DAYS)
    cutoff = timezone.now() - grace

    eligible = list(
        ItemInstance.objects.filter(destroyed_at__lt=cutoff, lore_value=0)
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
    for instance in eligible:
        hard_delete_item_instance(instance)
    return len(eligible)
