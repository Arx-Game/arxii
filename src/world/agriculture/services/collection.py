"""Food collection dispatch — mirrors ``collect_org_income``."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from world.agriculture.models import FieldDetails, FoodStockpile
from world.agriculture.services.domain import (
    max_food_capacity,
    resolve_domain_for_feature,
)
from world.agriculture.types import FoodCollectionResult


def _collection_band_pct(success_level: int) -> int | None:
    """Percent of the gathered pool that lands for this band; None = catastrophe.

    Reuses the same band shape as ``world.currency.services._collection_band_pct``
    but reads the constant directly (read-only — does NOT modify the shared
    constant).
    """
    from world.currency.constants import COLLECTION_BAND_PCTS  # noqa: PLC0415

    for floor, pct in COLLECTION_BAND_PCTS:
        if success_level >= floor:
            return pct
    return None


@transaction.atomic
def collect_field_food(character, field_instance) -> FoodCollectionResult:
    """One active collection dispatch from a Field's uncollected pool.

    Mirrors ``collect_org_income``: zeroes the pool (food left with the
    collector regardless of outcome), rolls a Food Collection check,
    applies the band percentage, and lands food into the domain's
    ``FoodStockpile`` (capped at max capacity from Granaries). Excess
    above capacity is lost (overflow).

    Args:
        character: The collecting character (ObjectDB).
        field_instance: The ``RoomFeatureInstance`` for the Field.

    Returns:
        ``FoodCollectionResult`` with gathered, landed, overflow, and
        catastrophe details.

    Raises:
        ValueError: If the pool is empty (nothing to collect).
    """
    from world.agriculture.constants import FOOD_COLLECTION_CHECK_NAME  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.scenes.action_constants import (  # noqa: PLC0415
        DIFFICULTY_VALUES,
        DifficultyChoice,
    )

    try:
        details = field_instance.field_details
    except FieldDetails.DoesNotExist:
        msg = "This field has no crop details."
        raise ValueError(msg) from None

    gathered = details.uncollected_pool
    if gathered <= 0:
        msg = "There is nothing waiting to be collected."
        raise ValueError(msg)

    # Zero the pool — food left with the collector regardless of outcome.
    details.uncollected_pool = 0
    details.save(update_fields=["uncollected_pool"])

    # Roll the check.
    check_type = CheckType.objects.filter(name__iexact=FOOD_COLLECTION_CHECK_NAME).first()
    success_level = 0  # unseeded world: unremarkable partial
    if check_type is not None:
        result = perform_check(
            character,
            check_type,
            target_difficulty=DIFFICULTY_VALUES[DifficultyChoice.NORMAL],
        )
        success_level = result.success_level

    pct = _collection_band_pct(success_level)
    if pct is None:
        # Catastrophe: the collector never made it back with the food.
        return FoodCollectionResult(
            gathered=gathered,
            landed=0,
            overflow=0,
            success_level=success_level,
            catastrophe=True,
        )

    landed = gathered * pct // 100

    # Land into the domain's stockpile, capped at max capacity.
    domain = resolve_domain_for_feature(field_instance)
    if domain is None:
        # No domain — food is collected but has nowhere to go.
        return FoodCollectionResult(
            gathered=gathered,
            landed=0,
            overflow=landed,
            success_level=success_level,
        )

    stockpile, _ = FoodStockpile.objects.get_or_create(domain=domain)
    capacity = max_food_capacity(domain)
    headroom = max(0, capacity - stockpile.stored)
    actual_landed = min(landed, headroom)
    overflow = landed - actual_landed

    stockpile.stored += actual_landed
    stockpile.last_collected_at = timezone.now()
    stockpile.save(update_fields=["stored", "last_collected_at"])

    return FoodCollectionResult(
        gathered=gathered,
        landed=actual_landed,
        overflow=overflow,
        success_level=success_level,
    )
