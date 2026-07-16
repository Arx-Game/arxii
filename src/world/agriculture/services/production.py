"""Production cron tick and config helpers for the agriculture system."""

from __future__ import annotations

import logging

from django.db import transaction

from world.agriculture.models import FieldDetails, FoodConfig
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.models import RoomFeatureInstance

logger = logging.getLogger(__name__)


def get_food_config() -> FoodConfig:
    """Lazy-create and return the FoodConfig singleton (pk=1)."""
    config, _ = FoodConfig.objects.get_or_create(pk=1)
    return config


def field_production_tick() -> dict[str, int]:
    """Daily cron: accrue food into every active Field's uncollected pool.

    Iterates active ``RoomFeatureInstance`` rows where
    ``feature_kind__service_strategy=FIELD``. For each, accrues
    ``crop_type.base_production × instance.level × config.production_rate_multiplier``
    into ``FieldDetails.uncollected_pool``.

    Per-Field atomic; exceptions isolated per instance (same as
    ``sanctum_resonance_generation_tick``).

    Returns:
        Telemetry dict with ``fields_processed`` and ``food_accrued``.
    """
    config = get_food_config()
    multiplier = config.production_rate_multiplier

    instances = (
        RoomFeatureInstance.objects.active()
        .select_related("feature_kind", "field_details", "field_details__crop_type")
        .filter(feature_kind__service_strategy=RoomFeatureServiceStrategy.FIELD)
    )

    fields_processed = 0
    food_accrued = 0

    for instance in instances:
        field_details = instance.field_details_or_none
        if field_details is None:
            continue
        try:
            _accrue_field(field_details, multiplier)
        except Exception:
            logger.exception(
                "Field production tick failed for instance %s; continuing.",
                instance.pk,
            )
            continue
        fields_processed += 1
        food_accrued += field_details.uncollected_pool

    return {
        "fields_processed": fields_processed,
        "food_accrued": food_accrued,
    }


@transaction.atomic
def _accrue_field(field_details: FieldDetails, multiplier: int) -> None:
    """Accrue one field's production into its uncollected pool."""
    base = field_details.crop_type.base_production
    level = field_details.feature_instance.level
    production = base * level * multiplier
    if production <= 0:
        return
    field_details.uncollected_pool += production
    field_details.save(update_fields=["uncollected_pool"])
