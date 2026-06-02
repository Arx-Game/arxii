"""Sanctum resonance generation cron tick (Plan 4 §F).

Iterates every active Sanctum's ``RoomFeatureInstance`` row and pays out
resonance to every weaver bound to it via a SANCTUM-target Thread.
Payout formula:

    income = max(thread.level, 1)
           × effective_value(room, resonance=sanctum.resonance_type)
           × LEVEL_MULTIPLIERS[sanctum.level - 1]
           × K_INCOME_RATE

``effective_value`` reads the cascade-summed total (authored ambient +
Homecoming-grown + future spell/event-source rows) so high-base wards
naturally boost income. ``K_INCOME_RATE`` is intentionally tiny — the
spec calls for "pretty small" gain rates, with the level multiplier
being the main player-feel knob (1.0 at L1, 6.0 at L5).

Bonus pass: each owner-or-active-covenant-member weaver receives
``+1 resonance per OTHER thread`` woven into the Sanctum (the
``SANCTUM_OWNER_BONUS`` source). Incentivizes recruiting weavers.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from world.covenants.constants import COVENANT_ORG_TYPE_NAME
from world.covenants.models import CharacterCovenantRole
from world.locations.constants import HolderType
from world.locations.services import effective_owner, effective_value
from world.magic.constants import TargetKind
from world.magic.models import SanctumDetails, SanctumOwnerMode, Thread
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.models import RoomFeatureInstance

LEVEL_MULTIPLIERS: tuple[Decimal, ...] = (
    Decimal("1.0"),
    Decimal("1.5"),
    Decimal("2.0"),
    Decimal("3.0"),
    Decimal("6.0"),
)
"""Per-Sanctum-level income multiplier. Index = level - 1. Plan 4 §F."""

K_INCOME_RATE: Decimal = Decimal("0.01")
"""Global per-tick conversion rate. Intentionally tiny; tune in playtest."""


def sanctum_resonance_generation_tick() -> dict[str, int]:
    """Pay out resonance income to every weaver of every active Sanctum.

    Returns a tiny telemetry dict (``sanctums_processed``,
    ``weavers_accrued``, ``bonus_recipients_accrued``) so the cron infrastructure
    can log the work each tick. Per-Sanctum work is atomic; an exception
    in one Sanctum is logged and isolated so others still pay out.
    """
    import logging  # noqa: PLC0415

    logger = logging.getLogger(__name__)

    instances = RoomFeatureInstance.objects.select_related(
        "feature_kind",
        "room_profile",
        "sanctum_details",
        "sanctum_details__resonance_type",
    ).filter(feature_kind__service_strategy=RoomFeatureServiceStrategy.SANCTUM)

    sanctums_processed = 0
    weavers_accrued = 0
    bonus_recipients_accrued = 0

    for instance in instances:
        sanctum = getattr(instance, "sanctum_details", None)  # noqa: GETATTR_LITERAL
        if sanctum is None:
            continue
        try:
            paid, bonus = _payout_for_sanctum(instance, sanctum)
        except Exception:
            logger.exception(
                "Sanctum %s payout failed; continuing with remaining Sanctums.",
                sanctum.pk,
            )
            continue
        sanctums_processed += 1
        weavers_accrued += paid
        bonus_recipients_accrued += bonus

    return {
        "sanctums_processed": sanctums_processed,
        "weavers_accrued": weavers_accrued,
        "bonus_recipients_accrued": bonus_recipients_accrued,
    }


@transaction.atomic
def _payout_for_sanctum(instance: RoomFeatureInstance, sanctum: SanctumDetails) -> tuple[int, int]:
    """Accumulate per-weaver income into ``SanctumPendingPayout`` rows.

    Plan 4 §F revised 2026-06-03 (well + absorb): the cron tick no longer
    calls ``grant_resonance`` directly. It grows the per-weaver pending
    pool, capped at ``SANCTUM_PENDING_PAYOUT_CAP`` total (sum of both
    pending fields). Weavers drain the pool via
    ``world.magic.services.sanctum_install.absorb_sanctum_pool`` when
    they physically visit the Sanctum's room.

    Per-Sanctum query budget (post-2026-06-03 review):
    1× pool, 1× threads.filter, 1× existing-payouts.filter,
    1× bulk_create(ignore_conflicts), 1× F()-increment .update per
    new-row or capped-row case. ``select_for_update`` on the payout
    rows + F() arithmetic close the race window against a concurrent
    ``absorb_sanctum_pool`` zeroing the pool.

    Returns ``(weavers_accrued, bonus_recipients_accrued)``.
    """

    threads = list(
        Thread.objects.select_related("owner").filter(
            target_sanctum_details=sanctum,
            target_kind=TargetKind.SANCTUM,
            retired_at__isnull=True,
        )
    )
    if not threads:
        return 0, 0

    pool = effective_value(instance.room_profile.objectdb, resonance=sanctum.resonance_type)
    if pool <= 0:
        return 0, 0

    level_multiplier = _multiplier_for_level(instance.level)

    # Compute per-thread weaving income in memory first.
    per_sheet_income: dict[int, int] = {}
    for thread in threads:
        strength = max(thread.level, 1)
        income = int(Decimal(strength) * Decimal(pool) * level_multiplier * K_INCOME_RATE)
        if income <= 0:
            continue
        per_sheet_income[thread.owner_id] = per_sheet_income.get(thread.owner_id, 0) + income
    weavers_accrued = _apply_pending_increments(sanctum, per_sheet_income, "pending_weaving")

    bonus_accrued = _accrue_owner_bonus(instance, sanctum, threads)
    return weavers_accrued, bonus_accrued


def _apply_pending_increments(
    sanctum: SanctumDetails, per_sheet_amount: dict[int, int], field: str
) -> int:
    """Bulk-create missing SanctumPendingPayout rows, then F()-update the field.

    ``field`` is one of ``"pending_weaving"`` / ``"pending_owner_bonus"``.
    The total (sum of both fields) is capped at
    ``SANCTUM_PENDING_PAYOUT_CAP``; we clamp the per-row increment to the
    remaining headroom *before* the F()-update so SQL-side arithmetic
    doesn't overshoot.

    Returns the number of weaver rows that actually received an
    increment > 0.
    """
    from django.db.models import F  # noqa: PLC0415

    from world.magic.models import SanctumPendingPayout  # noqa: PLC0415
    from world.magic.models.sanctum import SANCTUM_PENDING_PAYOUT_CAP  # noqa: PLC0415

    if not per_sheet_amount:
        return 0

    # Bulk-create any missing rows (race-safe via ignore_conflicts).
    SanctumPendingPayout.objects.bulk_create(
        [
            SanctumPendingPayout(
                sanctum=sanctum,
                weaver_character_sheet_id=sheet_id,
            )
            for sheet_id in per_sheet_amount
        ],
        ignore_conflicts=True,
    )

    # Lock the rows we're about to mutate; read current pending totals
    # so we can clamp to the cap without an SQL-side `LEAST(..., cap)`
    # expression (portable + cheap on small numbers of weavers).
    existing = {
        p.weaver_character_sheet_id: p
        for p in SanctumPendingPayout.objects.select_for_update().filter(
            sanctum=sanctum,
            weaver_character_sheet_id__in=per_sheet_amount.keys(),
        )
    }

    accrued_count = 0
    for sheet_id, requested in per_sheet_amount.items():
        payout = existing.get(sheet_id)
        if payout is None:
            continue
        remaining = SANCTUM_PENDING_PAYOUT_CAP - payout.total_pending()
        if remaining <= 0:
            continue  # well is full; tick no-op until absorbed
        actual = min(requested, remaining)
        if actual <= 0:
            continue
        # F() arithmetic so a concurrent absorb resetting the field to 0
        # can't be clobbered by a stale in-memory snapshot.
        SanctumPendingPayout.objects.filter(pk=payout.pk).update(**{field: F(field) + actual})
        # SharedMemoryModel keeps the bulk_created instance in its identity
        # map; the `.update()` bypasses ORM save() so the cached row's
        # ``pending_*`` value stays stale until refresh. Refresh so subsequent
        # ``objects.get(...)`` calls return the new value, not the cache.
        payout.refresh_from_db(fields=[field, "updated_at"])
        accrued_count += 1
    return accrued_count


def _multiplier_for_level(level: int) -> Decimal:
    """Clamp to the LEVEL_MULTIPLIERS table. Future levels reuse the top entry."""
    if level < 1:
        return LEVEL_MULTIPLIERS[0]
    if level > len(LEVEL_MULTIPLIERS):
        return LEVEL_MULTIPLIERS[-1]
    return LEVEL_MULTIPLIERS[level - 1]


def _accrue_owner_bonus(
    instance: RoomFeatureInstance,
    sanctum: SanctumDetails,
    threads: list[Thread],
) -> int:
    """+1 per other thread for owner-or-active-covenant-member weavers (into pending pool)."""
    if len(threads) <= 1:
        return 0  # Need at least 2 threads for "other thread" bonus to be positive.

    recipient_sheet_ids = _bonus_recipient_sheet_ids(instance, sanctum, threads)
    if not recipient_sheet_ids:
        return 0

    other_threads_per_recipient = len(threads) - 1
    per_sheet_bonus = {
        thread.owner_id: other_threads_per_recipient
        for thread in threads
        if thread.owner_id in recipient_sheet_ids
    }
    return _apply_pending_increments(sanctum, per_sheet_bonus, "pending_owner_bonus")


def _bonus_recipient_sheet_ids(
    instance: RoomFeatureInstance,
    sanctum: SanctumDetails,
    threads: list[Thread],
) -> set[int]:
    """Determine which weavers qualify for the owner/member bonus this tick."""
    ownership = effective_owner(instance.room_profile.objectdb)
    if ownership is None:
        return set()
    woven_sheet_ids = {t.owner_id for t in threads}
    if sanctum.owner_mode == SanctumOwnerMode.PERSONAL:
        return _personal_bonus_recipients(ownership, woven_sheet_ids)
    return _covenant_bonus_recipients(ownership, woven_sheet_ids)


def _personal_bonus_recipients(ownership, woven_sheet_ids: set[int]) -> set[int]:
    if ownership.holder_type != HolderType.PERSONA:
        return set()
    owner_sheet_id = ownership.holder_persona.character_sheet_id
    return {owner_sheet_id} if owner_sheet_id in woven_sheet_ids else set()


def _covenant_bonus_recipients(ownership, woven_sheet_ids: set[int]) -> set[int]:
    if ownership.holder_type != HolderType.ORGANIZATION:
        return set()
    if ownership.holder_organization.org_type.name != COVENANT_ORG_TYPE_NAME:
        return set()
    covenant = ownership.holder_organization.covenant
    active_member_sheet_ids = set(
        CharacterCovenantRole.objects.filter(covenant=covenant, left_at__isnull=True).values_list(
            "character_sheet_id", flat=True
        )
    )
    return woven_sheet_ids & active_member_sheet_ids
