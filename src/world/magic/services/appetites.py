"""Appetite anima economy (#2853): upkeep drains, glut decay, Ravenous, regen skip.

The upkeep shape mirrors the Somehow Always Broke purse drain: config keyed on
a Distinction, per-period receipt rows for idempotency, DRAIN-phased crons.
Floors mean starvation dims — it never kills by itself.
"""

from __future__ import annotations

from datetime import date, timedelta
import logging

from django.utils import timezone

from world.magic.models.anima import CharacterAnima
from world.magic.models.appetites import (
    AppetitePeriod,
    AppetiteUpkeep,
    AppetiteUpkeepReceipt,
)
from world.species.appetites import (
    APPETITE_TAGS,
    RAVENOUS_MAX_SEVERITY,
    RAVENOUS_THRESHOLD_PERCENT,
)

logger = logging.getLogger(__name__)


def appetite_holder_sheet_ids() -> set[int]:
    """CharacterSheet pks holding any appetite distinction (no natural anima regen)."""
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    return set(
        CharacterDistinction.objects.filter(
            distinction__tags__slug__in=APPETITE_TAGS,
        ).values_list("character_id", flat=True)
    )


def _week_start(today: date) -> date:
    """Monday of *today*'s week — matches the weekly-rollover anchor day."""
    return today - timedelta(days=today.weekday())


def appetite_upkeep_tick(period: str) -> int:
    """Run one period's appetite drains. Returns the count of characters drained.

    Idempotent per (holder, config, period_start) via receipts; the drain never
    takes ``current`` below ``floor_percent`` of maximum. Glut never satisfies
    the floor — it decays separately and cannot be hoarded against upkeep.
    """
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    today = timezone.now().date()
    period_start = today if period == AppetitePeriod.DAILY else _week_start(today)
    drained_count = 0
    configs = AppetiteUpkeep.objects.filter(period=period).select_related("distinction")
    for config in configs:
        holder_sheet_ids = CharacterDistinction.objects.filter(
            distinction=config.distinction
        ).values_list("character_id", flat=True)
        animas = CharacterAnima.objects.filter(character_id__in=list(holder_sheet_ids))
        for anima in animas:
            receipt, created = AppetiteUpkeepReceipt.objects.get_or_create(
                character_sheet_id=anima.character_id,
                upkeep=config,
                period_start=period_start,
            )
            if not created:
                continue
            # Ceil, not floor-division (#3001 ruling): 10% of a 105 pool holds 11
            # back, so a small floor never rounds away to nothing.
            floor = -(-anima.maximum * config.floor_percent // 100)
            drain = min(config.amount, max(0, anima.current - floor))
            if drain:
                anima.current -= drain
                anima.save(update_fields=["current"])
                drained_count += 1
            receipt.drained = drain
            receipt.save(update_fields=["drained"])
            reconcile_ravenous(anima.character)
    return drained_count


def decay_glut_tick() -> int:
    """Daily glut decay (#2853 ruled: a temporary high, not a tank). Returns rows touched."""
    from world.species.appetites import GLUT_DECAY_PER_DAY  # noqa: PLC0415

    touched = 0
    for anima in CharacterAnima.objects.filter(glut__gt=0):
        anima.glut = max(0, anima.glut - GLUT_DECAY_PER_DAY)
        anima.save(update_fields=["glut"])
        touched += 1
    return touched


def hunger_severity(anima: CharacterAnima) -> int:
    """Map hunger depth to a Ravenous severity (0 = not hungry). Glut never quiets it."""
    if anima.maximum <= 0:
        return 0
    threshold = (anima.maximum * RAVENOUS_THRESHOLD_PERCENT) // 100
    if threshold <= 0 or anima.current > threshold:
        return 0
    depth = threshold - anima.current
    return 1 + min(RAVENOUS_MAX_SEVERITY - 1, (depth * (RAVENOUS_MAX_SEVERITY - 1)) // threshold)


def reconcile_ravenous(sheet) -> None:
    """Sync the Ravenous condition to the sheet's hunger depth (appetite holders only)."""
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        decay_condition_severity,
        remove_condition,
    )
    from world.species.appetites import AppetiteKind, appetite_for  # noqa: PLC0415
    from world.species.factories import ensure_ravenous_condition  # noqa: PLC0415

    if sheet is None:
        return
    character = sheet.character
    if character is None:
        return
    anima = sheet.anima_or_none
    template = ensure_ravenous_condition()
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    instance = ConditionInstance.objects.filter(
        target=character, condition=template, resolved_at__isnull=True
    ).first()
    if appetite_for(sheet) == AppetiteKind.NONE or anima is None:
        target_severity = 0
    else:
        target_severity = hunger_severity(anima)
    if target_severity <= 0:
        if instance is not None:
            remove_condition(character, template)
        return
    if instance is None:
        from world.conditions.services import apply_condition  # noqa: PLC0415

        apply_condition(character, template, severity=target_severity)
    elif target_severity > instance.severity:
        advance_condition_severity(instance, target_severity - instance.severity)
    elif target_severity < instance.severity:
        decay_condition_severity(instance, instance.severity - target_severity)


def appetite_daily_tick() -> None:
    """Daily appetite pass: DAILY upkeep drains + glut decay."""
    drained = appetite_upkeep_tick(AppetitePeriod.DAILY)
    decayed = decay_glut_tick()
    if drained or decayed:
        logger.info("Appetite daily tick: %d drained, %d glut rows decayed.", drained, decayed)


def appetite_weekly_tick() -> None:
    """Weekly appetite pass: WEEKLY upkeep drains (vampires)."""
    drained = appetite_upkeep_tick(AppetitePeriod.WEEKLY)
    if drained:
        logger.info("Appetite weekly tick: %d drained.", drained)
