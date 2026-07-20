"""Common-gem value buckets (Build 0b slice 5).

Common gems are never instanced — they live as a per-tier aggregate value that mining
credits and bulk crafting spends. These helpers own the get/credit/spend of that value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.items.exceptions import InsufficientCommonGems
from world.items.gems.models import CommonGemBucket

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import MaterialCategory


def common_gem_value(character_sheet: CharacterSheet, tier: MaterialCategory) -> int:
    """Return the common-gem value ``character_sheet`` holds in ``tier`` (0 if none)."""
    bucket = CommonGemBucket.objects.filter(character_sheet=character_sheet, tier=tier).first()
    return bucket.value if bucket is not None else 0


def credit_common_gems(
    character_sheet: CharacterSheet, tier: MaterialCategory, value: int
) -> CommonGemBucket:
    """Add ``value`` to the ``(character_sheet, tier)`` bucket, creating it if needed."""
    if value < 0:
        msg = "Cannot credit a negative common-gem value."
        raise ValueError(msg)
    with transaction.atomic():
        bucket, created = CommonGemBucket.objects.get_or_create(
            character_sheet=character_sheet, tier=tier, defaults={"value": value}
        )
        if not created:
            # Canonical SharedMemoryModel mutation (ADR-0008): mutate the cached attribute
            # then save — NOT F()+update, which bypasses and staleifies the identity map.
            bucket.value += value
            bucket.save(update_fields=["value"])
    return bucket


def spend_common_gems(character_sheet: CharacterSheet, tier: MaterialCategory, value: int) -> None:
    """Spend ``value`` from the ``(character_sheet, tier)`` bucket.

    Raises ``InsufficientCommonGems`` if the bucket holds less than ``value`` (nothing is
    spent in that case).
    """
    if value <= 0:
        return
    with transaction.atomic():
        bucket = CommonGemBucket.objects.filter(character_sheet=character_sheet, tier=tier).first()
        if bucket is None or bucket.value < value:
            raise InsufficientCommonGems
        # Canonical SharedMemoryModel mutation (ADR-0008): mutate the cached attr then save.
        bucket.value -= value
        bucket.save(update_fields=["value"])
