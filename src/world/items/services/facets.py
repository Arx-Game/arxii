"""Services: facet attachment / removal on item instances."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from django.db import transaction

from world.items.exceptions import (
    CraftingNotConfigured,
    FacetAlreadyAttached,
    FacetCapacityExceeded,
)
from world.items.models import EquippedItem, ItemFacet, ItemInstance, QualityTier

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.magic.models import Facet


def assert_facet_attachable(item_instance: ItemInstance, facet: Facet) -> None:
    """Raise if ``facet`` cannot be attached to ``item_instance``.

    Raises:
        FacetAlreadyAttached: already present on the item.
        FacetCapacityExceeded: item is at its template's facet_capacity.
    """
    if item_instance.item_facets.filter(facet=facet).exists():
        raise FacetAlreadyAttached
    # Inherent facets (#3776 Task 4) are the item's own identity, auto-stamped by
    # stamp_inherent_facets — they never count against a crafter's facet_capacity.
    crafted_facet_count = item_instance.item_facets.filter(is_inherent=False).count()
    if crafted_facet_count >= item_instance.template.facet_capacity:
        raise FacetCapacityExceeded


@transaction.atomic
def attach_facet_to_item(
    *,
    crafter: AccountDB,
    item_instance: ItemInstance,
    facet: Facet,
    attachment_quality_tier: QualityTier,
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
    assert_facet_attachable(item_instance, facet)
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
        equipped.character.character.equipped_items.invalidate()
    return row


@transaction.atomic
def stamp_inherent_facets(item_instance: ItemInstance) -> None:
    """Create an ItemFacet(is_inherent=True) row for every facet the template carries.

    Idempotent — safe to call more than once; skips any facet the instance already
    carries (inherent or crafter-attached) rather than only its own prior stamps, so
    a re-run can never collide with the (item_instance, facet) unique constraint.
    Does not check facet_capacity: inherent facets are the item's own identity, not
    a crafter's creative addition.

    attachment_quality_tier is a required FK with no schema default — inherent
    facets weren't crafted, so there's no natural quality to record. Resolves the
    baseline tier via QualityTier.for_score(0) (reusing the model's own "lowest
    tier" resolution) rather than inventing a new convention.

    Raises:
        CraftingNotConfigured: No ``QualityTier`` rows are seeded (``for_score``
            returns ``None`` only in an unconfigured deployment) — same guard as
            the sibling call site in ``crafting/quality.py``.
    """
    existing_facet_ids = set(item_instance.item_facets.values_list("facet_id", flat=True))
    inherent_facets = item_instance.template.inherent_facets.exclude(id__in=existing_facet_ids)
    if not inherent_facets.exists():
        return
    baseline_tier = QualityTier.for_score(0)
    if baseline_tier is None:
        raise CraftingNotConfigured
    for facet in inherent_facets:
        ItemFacet.objects.create(
            item_instance=item_instance,
            facet=facet,
            is_inherent=True,
            applied_by_account=None,
            attachment_quality_tier=baseline_tier,
        )


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
        equipped.character.character.equipped_items.invalidate()
