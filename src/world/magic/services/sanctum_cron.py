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
from world.magic.constants import GainSource, TargetKind
from world.magic.models import SanctumDetails, SanctumOwnerMode, Thread
from world.magic.services.resonance import grant_resonance
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
    ``weaver_grants``, ``owner_bonus_grants``) so the cron infrastructure
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
    weaver_grants = 0
    owner_bonus_grants = 0

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
        weaver_grants += paid
        owner_bonus_grants += bonus

    return {
        "sanctums_processed": sanctums_processed,
        "weaver_grants": weaver_grants,
        "owner_bonus_grants": owner_bonus_grants,
    }


@transaction.atomic
def _payout_for_sanctum(instance: RoomFeatureInstance, sanctum: SanctumDetails) -> tuple[int, int]:
    """Pay weavers and bonus recipients for one Sanctum. Returns (paid_count, bonus_count)."""
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
    paid = 0
    for thread in threads:
        strength = max(thread.level, 1)
        income = int(Decimal(strength) * Decimal(pool) * level_multiplier * K_INCOME_RATE)
        if income <= 0:
            continue
        grant_resonance(
            character_sheet=thread.owner,
            resonance=sanctum.resonance_type,
            amount=income,
            source=GainSource.SANCTUM_WEAVING,
            sanctum_details=sanctum,
        )
        paid += 1

    bonus = _pay_owner_bonus(instance, sanctum, threads)
    return paid, bonus


def _multiplier_for_level(level: int) -> Decimal:
    """Clamp to the LEVEL_MULTIPLIERS table. Future levels reuse the top entry."""
    if level < 1:
        return LEVEL_MULTIPLIERS[0]
    if level > len(LEVEL_MULTIPLIERS):
        return LEVEL_MULTIPLIERS[-1]
    return LEVEL_MULTIPLIERS[level - 1]


def _pay_owner_bonus(
    instance: RoomFeatureInstance,
    sanctum: SanctumDetails,
    threads: list[Thread],
) -> int:
    """+1 resonance per other thread for owner-or-active-covenant-member weavers."""
    if len(threads) <= 1:
        return 0  # Need at least 2 threads for "other thread" bonus to be positive.

    recipient_sheet_ids = _bonus_recipient_sheet_ids(instance, sanctum, threads)
    if not recipient_sheet_ids:
        return 0

    other_threads_per_recipient = len(threads) - 1
    bonus_count = 0
    for thread in threads:
        if thread.owner_id not in recipient_sheet_ids:
            continue
        grant_resonance(
            character_sheet=thread.owner,
            resonance=sanctum.resonance_type,
            amount=other_threads_per_recipient,
            source=GainSource.SANCTUM_OWNER_BONUS,
            sanctum_details=sanctum,
        )
        bonus_count += 1
    return bonus_count


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
