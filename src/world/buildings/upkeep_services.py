"""Phase E — Weekly upkeep, decay, and recovery (#676).

Flow per RL week:

1. ``apply_weekly_upkeep_all_buildings()`` walks every building with
   active project instances and tries to deduct upkeep.
2. For each building: sum the ``weekly_upkeep_cost`` over all of its
   active (polish > 0) instances. Try to deduct that total from the
   owner's body wallet (``CurrencyBalance.gold``) all-or-nothing.
3. On success: reset every instance's ``consecutive_missed_upkeep`` to 0
   and stamp ``last_upkeep_paid_at`` on each.
4. On miss (insufficient gold OR no owner OR no wallet): apply one tick
   of decay to the lowest-priority active instance via
   ``apply_one_decay_tick``.
5. When a decay tick drains an instance's polish to 0 in every
   category, mark it ``decayed_at = now``. If the building's
   *every* active instance is now drained, flip
   ``is_accessible = False`` and stamp ``dormant_since``.

Recovery:

* ``apply_restoration_project(building)`` flips ``is_accessible = True``
  and clears ``dormant_since``. Decayed instances stay at 0 polish.
* ``apply_mass_feature_restoration(building)`` walks every decayed
  instance, refills its per-category polish to the template's original
  values, and recomputes the building's aggregate ``BuildingPolish``
  rows. Costs ~10% of the summed original polish (admin-decided in
  practice; this function does the rebuild, not the deduction).

Numbers are admin-tunable via ``world.buildings.constants``.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from world.buildings.constants import (
    DECAY_ACCELERATION_FACTOR,
    DECAY_BASE_AMOUNT,
)
from world.buildings.models import (
    Building,
    BuildingPolish,
    BuildingProjectInstance,
    BuildingProjectInstancePolish,
)
from world.buildings.polish_services import recompute_persona_prestige_from_dwellings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wallet access
# ---------------------------------------------------------------------------


def _resolve_owner_wallet(building: Building):
    """Walk ``building.owner_persona → character_sheet → character → currency_balance``.

    Returns the CurrencyBalance row, or None when the building has no
    owner or the body has never had a wallet created. Persona / sheet /
    character relations are non-null at the DB level, so we only guard
    the two breaking links: missing owner, and the optional wallet row.
    """
    from world.items.models import CurrencyBalance  # noqa: PLC0415

    if building.owner_persona is None:
        return None
    try:
        return building.owner_persona.character_sheet.character.currency_balance
    except CurrencyBalance.DoesNotExist:
        return None


def _building_active_instances(building: Building):
    """Active = at least one polish row > 0 (not fully decayed yet)."""
    return (
        BuildingProjectInstance.objects.filter(building=building)
        .annotate(total_polish=Sum("polish_by_category__value"))
        .filter(total_polish__gt=0)
    )


def _building_total_upkeep(building: Building) -> int:
    """Sum weekly_upkeep_cost across all active instances on this building."""
    return (
        _building_active_instances(building).aggregate(total=Sum("weekly_upkeep_cost"))["total"]
        or 0
    )


# ---------------------------------------------------------------------------
# Decay (one tick on the outermost active instance)
# ---------------------------------------------------------------------------


def _decay_amount_for(consecutive_missed: int) -> int:
    """Accelerating-curve decay amount for the Nth consecutive miss (N≥1).

    ``DECAY_BASE_AMOUNT × DECAY_ACCELERATION_FACTOR**(N-1)``. First miss
    is the base; second is 1.5x base; third is 2.25x base; …
    """
    if consecutive_missed <= 0:
        return 0
    return int(DECAY_BASE_AMOUNT * (DECAY_ACCELERATION_FACTOR ** (consecutive_missed - 1)))


@transaction.atomic
def apply_one_decay_tick(building: Building) -> BuildingProjectInstance | None:
    """Decay one tick on the lowest-priority active instance of ``building``.

    Returns the touched instance (or None when nothing's left to decay).
    Increments that instance's ``consecutive_missed_upkeep`` first, then
    subtracts the curve's decay across each of its polish-by-category
    rows. Polish floors at 0. When the instance's total polish hits 0,
    marks ``decayed_at = now`` and resets ``consecutive_missed_upkeep``
    so the next-priority instance starts at tick 1 next week.
    """
    instance = _building_active_instances(building).order_by("decay_priority", "pk").first()
    if instance is None:
        return None

    # Single-row increment under transaction.atomic — no race; F not needed.
    instance.consecutive_missed_upkeep = instance.consecutive_missed_upkeep + 1
    instance.save(update_fields=["consecutive_missed_upkeep"])

    decay_amount = _decay_amount_for(instance.consecutive_missed_upkeep)
    polish_rows = list(instance.polish_by_category.select_related("category"))
    for row in polish_rows:
        new_value = max(0, row.value - decay_amount)
        if new_value == row.value:
            continue
        delta = row.value - new_value
        row.value = new_value
        row.save(update_fields=["value"])
        # Per-instance .save() (not queryset .update()) so SharedMemoryModel
        # identity-map cache reflects the new aggregate value immediately.
        try:
            bp = BuildingPolish.objects.get(building=building, category=row.category)
        except BuildingPolish.DoesNotExist:
            continue
        bp.value = max(0, bp.value - delta)
        bp.save(update_fields=["value"])

    # If the instance is now fully drained, mark it and reset its
    # miss counter so the next-priority instance starts fresh.
    total_polish = instance.polish_by_category.aggregate(total=Sum("value"))["total"] or 0
    if total_polish == 0:
        instance.decayed_at = timezone.now()
        instance.consecutive_missed_upkeep = 0
        instance.save(update_fields=["decayed_at", "consecutive_missed_upkeep"])

    if building.owner_persona_id is not None:
        recompute_persona_prestige_from_dwellings(building.owner_persona)

    return instance


# ---------------------------------------------------------------------------
# Weekly upkeep (per building)
# ---------------------------------------------------------------------------


def _reset_building_upkeep_counters(building: Building) -> None:
    """Reset every instance's miss counter + stamp last_upkeep_paid_at.

    Per-row .save() (not queryset .update()) so the SharedMemoryModel
    identity-map cache reflects the new counter state for any in-memory
    BuildingProjectInstance that callers already hold.
    """
    now = timezone.now()
    for instance in BuildingProjectInstance.objects.filter(building=building):
        instance.consecutive_missed_upkeep = 0
        instance.last_upkeep_paid_at = now
        instance.save(update_fields=["consecutive_missed_upkeep", "last_upkeep_paid_at"])


def _try_dormancy_flip(building: Building) -> bool:
    """When zero active instances remain, flip is_accessible False + stamp.

    Returns True iff the building was just flipped to dormant on this call.
    """
    if _building_active_instances(building).exists():
        return False
    if not building.is_accessible:
        return False
    building.is_accessible = False
    building.dormant_since = timezone.now()
    building.save(update_fields=["is_accessible", "dormant_since"])
    return True


@transaction.atomic
def apply_weekly_upkeep_for_building(building: Building) -> bool:
    """Try one weekly upkeep cycle on ``building``. Returns True iff paid.

    All-or-nothing: either the full upkeep deducts from the owner's
    wallet (success) or one tick of decay fires on the outermost active
    instance (miss). After a miss, checks dormancy.
    """
    total = _building_total_upkeep(building)
    if total <= 0:
        # No active instances → nothing to upkeep, nothing to decay.
        return True

    wallet = _resolve_owner_wallet(building)
    if wallet is not None and wallet.gold >= total:
        wallet.gold = wallet.gold - total
        wallet.save(update_fields=["gold"])
        _reset_building_upkeep_counters(building)
        return True

    apply_one_decay_tick(building)
    _try_dormancy_flip(building)
    return False


@transaction.atomic
def apply_weekly_upkeep_all_buildings() -> tuple[int, int]:
    """Sweep all buildings with active instances. Returns (paid, missed) counts.

    Single transaction so a mid-sweep failure doesn't leave half the
    cron tick applied.
    """
    paid = missed = 0
    seen_building_ids: set[int] = set()
    for instance in BuildingProjectInstance.objects.select_related("building").iterator():
        if instance.building_id in seen_building_ids:
            continue
        seen_building_ids.add(instance.building_id)
        if apply_weekly_upkeep_for_building(instance.building):
            paid += 1
        else:
            missed += 1
    logger.info("buildings.upkeep_sweep: paid=%d missed=%d", paid, missed)
    return paid, missed


# ---------------------------------------------------------------------------
# Recovery — restoration projects
# ---------------------------------------------------------------------------


@transaction.atomic
def apply_restoration_project(building: Building) -> bool:
    """Flip a dormant building back to accessible.

    Returns True iff the building was dormant and is now accessible.
    Decayed instances stay at 0 polish; mass-restoration handles those.
    """
    if building.is_accessible:
        return False
    building.is_accessible = True
    building.dormant_since = None
    building.save(update_fields=["is_accessible", "dormant_since"])
    return True


@transaction.atomic
def apply_mass_feature_restoration(building: Building) -> int:
    """Refill every decayed instance on ``building`` to its template's polish.

    Returns the count of instances restored. Each instance's
    polish-by-category rows reset to the template's original polish
    increments; the building's aggregate BuildingPolish is rebuilt from
    scratch by summing the instance rows.

    Does NOT charge gold — caller deducts based on
    ``MASS_RESTORATION_COST_FRACTION`` of the building's summed
    original polish (admin-priced in practice).
    """
    decayed = list(
        BuildingProjectInstance.objects.filter(
            building=building, decayed_at__isnull=False
        ).select_related("template")
    )
    if not decayed:
        return 0

    for instance in decayed:
        increments = list(instance.template.polish_increment_rows.select_related("category"))
        # Refill instance polish to template values.
        for inc in increments:
            ip, _created = BuildingProjectInstancePolish.objects.get_or_create(
                instance=instance, category=inc.category, defaults={"value": 0}
            )
            ip.value = inc.value
            ip.save(update_fields=["value"])
        instance.decayed_at = None
        instance.consecutive_missed_upkeep = 0
        instance.save(update_fields=["decayed_at", "consecutive_missed_upkeep"])

    _rebuild_building_polish_aggregate(building)
    if building.owner_persona_id is not None:
        recompute_persona_prestige_from_dwellings(building.owner_persona)
    return len(decayed)


def _rebuild_building_polish_aggregate(building: Building) -> None:
    """Re-derive every BuildingPolish row from the sum of instance polish rows.

    Used after mass-restoration to ensure the aggregate matches the
    instance state exactly (in case admin actions or decay drifted them).
    """
    BuildingPolish.objects.filter(building=building).delete()
    sums = (
        BuildingProjectInstancePolish.objects.filter(instance__building=building)
        .values("category")
        .annotate(total=Sum("value"))
    )
    for row in sums:
        if row["total"] <= 0:
            continue
        BuildingPolish.objects.create(
            building=building, category_id=row["category"], value=row["total"]
        )
