"""Material value buckets (#2540 slice 2, generalized from Build 0b's gem-only buckets).

Bulk materials are never instanced — they live as a per-category aggregate value that
mining/production credits and bulk crafting spends. These helpers own the
get/credit/spend of that value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.items.exceptions import InsufficientMaterialStock
from world.items.materials_models import MaterialBucket

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import MaterialCategory


def material_value(character_sheet: CharacterSheet, material_category: MaterialCategory) -> int:
    """Return the material value ``character_sheet`` holds in ``material_category``, 0 if none."""
    bucket = MaterialBucket.objects.filter(
        character_sheet=character_sheet, material_category=material_category
    ).first()
    return bucket.value if bucket is not None else 0


def credit_materials(
    character_sheet: CharacterSheet, material_category: MaterialCategory, value: int
) -> MaterialBucket:
    """Add ``value`` to the ``(character_sheet, material_category)`` bucket; create it if needed.

    Row-locked before the read-modify-write when the bucket already exists (mirrors
    ``currency.services.transfer``'s source/destination lock) — #2540 slice 3 review:
    concurrent same-bucket credits (e.g. two boon accepts crediting one asker) are a
    realistic race now, not just a theoretical one.
    """
    if value < 0:
        msg = "Cannot credit a negative material value."
        raise ValueError(msg)
    with transaction.atomic():
        bucket, created = MaterialBucket.objects.get_or_create(
            character_sheet=character_sheet,
            material_category=material_category,
            defaults={"value": value},
        )
        if not created:
            # Lock before mutating — get_or_create's own lookup above is unlocked, so
            # re-fetch under the lock rather than trust that stale read.
            bucket = MaterialBucket.objects.select_for_update().get(pk=bucket.pk)
            # Canonical SharedMemoryModel mutation (ADR-0008): mutate the cached attribute
            # then save — NOT F()+update, which bypasses and staleifies the identity map.
            bucket.value += value
            bucket.save(update_fields=["value"])
    return bucket


def spend_materials(
    character_sheet: CharacterSheet, material_category: MaterialCategory, value: int
) -> None:
    """Spend ``value`` from the ``(character_sheet, material_category)`` bucket.

    Raises ``InsufficientMaterialStock`` if the bucket holds less than ``value`` (nothing
    is spent in that case). Row-locked before the check (mirrors
    ``currency.services.transfer``'s source lock) — #2540 slice 3 review: concurrent
    same-bucket drains (e.g. two boon accepts against one NPC's bucket) are a realistic
    race now, not just a theoretical one; without the lock, both reads could pass the
    sufficiency check before either write lands, overdrawing the bucket.
    """
    if value <= 0:
        return
    with transaction.atomic():
        bucket = (
            MaterialBucket.objects.select_for_update()
            .filter(character_sheet=character_sheet, material_category=material_category)
            .first()
        )
        if bucket is None or bucket.value < value:
            raise InsufficientMaterialStock
        # Canonical SharedMemoryModel mutation (ADR-0008): mutate the cached attr then save.
        bucket.value -= value
        bucket.save(update_fields=["value"])
