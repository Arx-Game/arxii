"""Services: facet attachment / removal on item instances."""

from __future__ import annotations

import contextlib

from django.db import transaction

from world.items.exceptions import FacetAlreadyAttached, FacetCapacityExceeded
from world.items.models import EquippedItem, ItemFacet, ItemInstance


@transaction.atomic
def attach_facet_to_item(
    *,
    crafter,  # AccountDB — the account applying the facet
    item_instance: ItemInstance,
    facet,  # world.magic.models.Facet
    attachment_quality_tier,  # QualityTier
) -> ItemFacet:
    """Attach ``facet`` to ``item_instance``.

    Args:
        crafter: The account performing the attachment.
        item_instance: The item receiving the facet.
        facet: The Facet to attach.
        attachment_quality_tier: The QualityTier at which the facet is attached.

    Returns:
        The newly created ItemFacet row.

    Raises:
        FacetAlreadyAttached: This facet is already attached to the item.
        FacetCapacityExceeded: The item is at the template's facet_capacity.
    """
    if item_instance.item_facets.filter(facet=facet).exists():
        raise FacetAlreadyAttached
    if item_instance.item_facets.count() >= item_instance.template.facet_capacity:
        raise FacetCapacityExceeded
    row = ItemFacet.objects.create(
        item_instance=item_instance,
        facet=facet,
        applied_by_account=crafter,
        attachment_quality_tier=attachment_quality_tier,
    )
    # Invalidate the ItemInstance's facet cache so the new row is visible.
    with contextlib.suppress(AttributeError):
        del item_instance.cached_item_facets
    # Invalidate handler caches for any wearer of this item.
    # Note: we do NOT use select_related("character") here — Evennia's idmapper
    # returns the cached Python object only via lazy FK access (which goes through
    # SharedMemoryModelBase.__call__). select_related bypasses __call__ and returns
    # a fresh Python object, meaning .equipped_items would be a different handler
    # instance that doesn't share the in-process cache.
    for equipped in EquippedItem.objects.filter(item_instance=item_instance):
        equipped.character.equipped_items.invalidate()
    return row


@transaction.atomic
def remove_facet_from_item(*, item_facet: ItemFacet) -> None:
    """Remove a facet attachment and invalidate wearers' handler caches.

    Args:
        item_facet: The ItemFacet row to delete.
    """
    instance = item_facet.item_instance
    item_facet.delete()
    # Invalidate the ItemInstance's facet cache so the removed row is no longer visible.
    with contextlib.suppress(AttributeError):
        del instance.cached_item_facets
    # Same select_related caveat — see attach_facet_to_item.
    for equipped in EquippedItem.objects.filter(item_instance=instance):
        equipped.character.equipped_items.invalidate()
