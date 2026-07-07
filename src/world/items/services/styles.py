"""Services: style attachment on item instances (#546)."""

from __future__ import annotations

import contextlib
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.items.exceptions import StyleAlreadyAttached, StyleCapacityExceeded
from world.items.models import AudacityTuning, EquippedItem, ItemInstance, ItemStyle, QualityTier

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.items.models import Style


def get_audacity_tuning() -> AudacityTuning:
    """Get-or-create the audacity tuning config singleton (pk=1, #2029)."""
    cfg = AudacityTuning.objects.cached_singleton()
    if cfg is None:
        cfg, _ = AudacityTuning.objects.get_or_create(pk=1)
    return cfg


def audacity_multiplier_for(style: Style) -> Decimal:
    """Return the tuned reward multiplier for ``style``'s audacity tier (#2029)."""
    return get_audacity_tuning().multiplier_for(style.audacity)


def assert_style_attachable(item_instance: ItemInstance, style: Style) -> None:
    """Raise if ``style`` cannot be attached to ``item_instance``.

    Raises:
        StyleAlreadyAttached: already present on the item.
        StyleCapacityExceeded: item is at its template's style_capacity.
    """
    if item_instance.item_styles.filter(style=style).exists():
        raise StyleAlreadyAttached
    if item_instance.item_styles.count() >= item_instance.template.style_capacity:
        raise StyleCapacityExceeded


@transaction.atomic
def attach_style_to_item(
    *,
    crafter: AccountDB,
    item_instance: ItemInstance,
    style: Style,
    attachment_quality_tier: QualityTier,
) -> ItemStyle:
    """Attach ``style`` to ``item_instance``.

    Args:
        crafter: The account performing the attachment.
        item_instance: The item receiving the style.
        style: The Style to attach.
        attachment_quality_tier: The QualityTier at which the style is attached.

    Returns:
        The newly created ItemStyle row.

    Raises:
        StyleAlreadyAttached: This style is already attached to the item.
        StyleCapacityExceeded: The item is at the template's style_capacity.
    """
    assert_style_attachable(item_instance, style)
    row = ItemStyle.objects.create(
        item_instance=item_instance,
        style=style,
        applied_by_account=crafter,
        attachment_quality_tier=attachment_quality_tier,
    )
    # Invalidate the ItemInstance's style cache so the new row is visible.
    with contextlib.suppress(AttributeError):
        del item_instance.cached_item_styles
    # Invalidate handler caches for any wearer of this item.
    # Note: we do NOT use select_related("character") here — Evennia's idmapper
    # returns the cached Python object only via lazy FK access (which goes through
    # SharedMemoryModelBase.__call__). select_related bypasses __call__ and returns
    # a fresh Python object, meaning .equipped_items would be a different handler
    # instance that doesn't share the in-process cache.
    for equipped in EquippedItem.objects.filter(item_instance=item_instance):
        equipped.character.equipped_items.invalidate()
    return row
