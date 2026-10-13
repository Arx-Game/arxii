"""Behavior-altering conditions on opponents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

if TYPE_CHECKING:
    from datetime import datetime

    from world.conditions.models import ConditionInstance


def _new_behavior_altering_conditions(objectdb_id: int, since: datetime) -> list[ConditionInstance]:
    """Behavior-altering ``ConditionInstance`` rows applied to *objectdb_id* since *since*."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return list(
        ConditionInstance.objects.filter(
            target_id=objectdb_id,
            condition__category__alters_behavior=True,
            applied_at__gte=since,
        ).select_related("condition")
    )


def _has_active_behavior_altering_condition(objectdb_id: int) -> bool:
    """True if *objectdb_id* currently carries an active behavior-altering condition.

    Mirrors ``CharacterSheet.in_control``'s canonical active-condition read
    (ADR-0024): not suppressed, or suppression has expired.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    not_suppressed = Q(is_suppressed=False)
    suppression_expired = Q(suppressed_until__isnull=False, suppressed_until__lt=timezone.now())
    return ConditionInstance.objects.filter(
        not_suppressed | suppression_expired,
        target_id=objectdb_id,
        condition__category__alters_behavior=True,
    ).exists()
