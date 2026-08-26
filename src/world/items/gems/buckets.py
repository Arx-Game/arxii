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
    """Add ``value`` to the ``(character_sheet, material_category)`` bucket; create it if needed."""
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
    is spent in that case).
    """
    if value <= 0:
        return
    with transaction.atomic():
        bucket = MaterialBucket.objects.filter(
            character_sheet=character_sheet, material_category=material_category
        ).first()
        if bucket is None or bucket.value < value:
            raise InsufficientMaterialStock
        # Canonical SharedMemoryModel mutation (ADR-0008): mutate the cached attr then save.
        bucket.value -= value
        bucket.save(update_fields=["value"])
