"""Weekly building upkeep — arrears-first, condition-tier slide/regain (#1930).

Flow per RL week, per building (mothballed buildings, and granted-but-not-yet-
activated property grants, are skipped entirely):

1. **Dwell decay** for above-normal tiers: EXTRAVAGANT slides back to
   EXCELLENT once its ``ABOVE_NORMAL_DWELL_DAYS`` dwell lapses, always.
   IMMACULATE holds past the dwell only while ``ultra_upkeep`` is on AND
   the premium (``ULTRA_UPKEEP_MULTIPLIER × weekly cost``) is paid this
   week; otherwise it slides to EXTRAVAGANT.
2. **Payment**: the summed ``weekly_upkeep_cost`` over the building's
   project instances deducts all-or-nothing from the owner's purse
   (audited ledger sink). Paid → miss counter resets; below-EXCELLENT
   buildings climb one tier per ``REGAIN_WEEKS_PER_TIER`` consecutive
   paid weeks.
3. **Miss**: arrears accrue (capped at ``ARREARS_CAP_WEEKS × weekly
   cost``); a building above EXCELLENT drops straight to EXCELLENT (no
   gala shine on credit); past ``GRACE_MISSES`` the tier slides one step
   per ``SLIP_WEEKS_PER_TIER`` further misses, floored at DECAYED.

Nonpayment NEVER mutates polish/feature rows — condition modulates the
prestige readout (``polish_services``); the walls are inviolate. Recovery
(settle / renovate / prepare / ultra toggle) lives in
``condition_services``. Numbers are PLACEHOLDER, tunable via
``world.buildings.constants``.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from world.buildings.constants import (
    ABOVE_NORMAL_DWELL_DAYS,
    ARREARS_CAP_WEEKS,
    GRACE_MISSES,
    REGAIN_WEEKS_PER_TIER,
    SLIP_WEEKS_PER_TIER,
    ULTRA_UPKEEP_MULTIPLIER,
    ConditionTier,
)
from world.buildings.models import Building, BuildingProjectInstance
from world.buildings.polish_services import recompute_persona_prestige_from_dwellings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wallet access
# ---------------------------------------------------------------------------


def _resolve_owner_purse(building: Building):
    """The owner's CharacterPurse (#925 ledger), or None with no owner.

    Re-pointed from the legacy items.CurrencyBalance wallet during #932 —
    upkeep now flows through the audited currency ledger as a sink.
    """
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    if building.owner_persona is None:
        return None
    return get_or_create_purse(building.owner_persona.character_sheet)


def building_weekly_upkeep(building: Building) -> int:
    """Sum ``weekly_upkeep_cost`` across all project instances on this building."""
    return (
        BuildingProjectInstance.objects.filter(building=building).aggregate(
            total=Sum("weekly_upkeep_cost")
        )["total"]
        or 0
    )


# ---------------------------------------------------------------------------
# Condition-tier movement
# ---------------------------------------------------------------------------


def set_condition_tier(building: Building, tier: int) -> None:
    """Set ``condition_tier`` (stamping ``condition_since``) + recompute prestige.

    No-op when the tier is unchanged. The single write path for tier
    movement — the weekly cycle and ``condition_services`` both go
    through here so the prestige readout can never drift from the tier.
    """
    if building.condition_tier == tier:
        return
    building.condition_tier = tier
    building.condition_since = timezone.now()
    building.save(update_fields=["condition_tier", "condition_since"])
    if building.owner_persona_id is not None:
        recompute_persona_prestige_from_dwellings(building.owner_persona)


def _sink_from_purse(purse, amount: int, reason: str) -> None:
    from world.currency.services import transfer  # noqa: PLC0415

    transfer(amount=amount, reason=reason, from_purse=purse)


def _apply_dwell_decay(building: Building, purse, weekly_total: int) -> None:
    """Slide above-normal tiers whose dwell has lapsed (step 1 of the cycle).

    IMMACULATE is held (dwell re-stamped) when ``ultra_upkeep`` is on and
    the premium is affordable — the premium is an additional pure sink on
    top of the normal weekly cost.
    """
    if building.condition_tier <= ConditionTier.EXCELLENT:
        return
    dwell = timedelta(days=ABOVE_NORMAL_DWELL_DAYS)
    if timezone.now() - building.condition_since < dwell:
        return

    if building.condition_tier == ConditionTier.IMMACULATE and building.ultra_upkeep:
        premium = ULTRA_UPKEEP_MULTIPLIER * weekly_total
        if purse is not None and premium > 0 and purse.balance >= premium:
            _sink_from_purse(purse, premium, f"ultra upkeep: building {building.pk}")
            building.condition_since = timezone.now()
            building.save(update_fields=["condition_since"])
            return

    set_condition_tier(building, building.condition_tier - 1)


def _apply_paid_week(building: Building) -> None:
    """Counter bookkeeping + slow tier regain after a successful payment."""
    building.consecutive_missed_upkeep = 0
    building.consecutive_paid_upkeep = building.consecutive_paid_upkeep + 1
    update_fields = ["consecutive_missed_upkeep", "consecutive_paid_upkeep"]
    if (
        building.condition_tier < ConditionTier.EXCELLENT
        and building.consecutive_paid_upkeep >= REGAIN_WEEKS_PER_TIER
    ):
        building.consecutive_paid_upkeep = 0
        building.save(update_fields=update_fields)
        set_condition_tier(building, building.condition_tier + 1)
        return
    building.save(update_fields=update_fields)


def _apply_missed_week(building: Building, weekly_total: int) -> None:
    """Arrears-first miss handling: bounded debt, grace, then tier slide."""
    building.consecutive_paid_upkeep = 0
    building.consecutive_missed_upkeep = building.consecutive_missed_upkeep + 1
    building.upkeep_arrears = min(
        building.upkeep_arrears + weekly_total,
        ARREARS_CAP_WEEKS * weekly_total,
    )
    building.save(
        update_fields=[
            "consecutive_paid_upkeep",
            "consecutive_missed_upkeep",
            "upkeep_arrears",
        ]
    )

    if building.condition_tier > ConditionTier.EXCELLENT:
        # No gala shine on credit — a missed normal payment above normal
        # drops straight back to EXCELLENT.
        set_condition_tier(building, ConditionTier.EXCELLENT)
        return

    misses_past_grace = building.consecutive_missed_upkeep - GRACE_MISSES
    if misses_past_grace > 0 and misses_past_grace % SLIP_WEEKS_PER_TIER == 0:
        set_condition_tier(building, max(ConditionTier.DECAYED, building.condition_tier - 1))


# ---------------------------------------------------------------------------
# Weekly upkeep (per building + sweep)
# ---------------------------------------------------------------------------


def _stamp_instances_paid(building: Building) -> None:
    """Stamp ``last_upkeep_paid_at`` on every instance after a paid week.

    Per-row .save() (not queryset .update()) so the SharedMemoryModel
    identity-map cache reflects the stamp for any in-memory instance.
    """
    now = timezone.now()
    for instance in BuildingProjectInstance.objects.filter(building=building):
        instance.last_upkeep_paid_at = now
        instance.save(update_fields=["last_upkeep_paid_at"])


@transaction.atomic
def apply_weekly_upkeep_for_building(building: Building) -> bool:
    """Run one weekly cycle on ``building``. Returns True iff paid (or free).

    Mothballed buildings are frozen — no dwell decay, no payment, no
    arrears (absence costs opportunity, never principal). Granted-but-not-yet-
    activated property grants (``property_granted_at`` set, ``property_activated_at``
    unset) are likewise exempt — the owner hasn't taken possession yet, so
    there's nothing to bill for.
    """
    if building.mothballed_at is not None:
        return True

    if building.property_granted_at is not None and building.property_activated_at is None:
        return True

    weekly_total = building_weekly_upkeep(building)
    purse = _resolve_owner_purse(building)

    _apply_dwell_decay(building, purse, weekly_total)

    if weekly_total <= 0:
        # Nothing to charge (style-only or featureless building) — the
        # dwell decay above still ran.
        return True

    if purse is not None and purse.balance >= weekly_total:
        _sink_from_purse(purse, weekly_total, f"upkeep: building {building.pk}")
        _stamp_instances_paid(building)
        _apply_paid_week(building)
        return True

    _apply_missed_week(building, weekly_total)
    return False


@transaction.atomic
def apply_weekly_upkeep_all_buildings() -> tuple[int, int]:
    """Sweep every building. Returns (paid, missed) counts.

    Walks ALL buildings (not just those with project instances) so
    above-normal dwell decay applies to style-only buildings too.
    Single transaction so a mid-sweep failure doesn't leave half the
    cron tick applied.
    """
    paid = missed = 0
    for building in Building.objects.select_related("owner_persona").iterator():
        if apply_weekly_upkeep_for_building(building):
            paid += 1
        else:
            missed += 1
    logger.info("buildings.upkeep_sweep: paid=%d missed=%d", paid, missed)
    return paid, missed
