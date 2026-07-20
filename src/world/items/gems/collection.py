"""Gem-side of the org income collection dispatch (Build 0b, domain-cron collection).

Mining accrues a mine's haul into *uncollected* pools on the holding's income stream
(``StreamCommonGemPool`` for common value, ``PendingRareFind`` for the stones). Per
Apostate's design, gems are **lumped with tax collection**: the same active
``collect_org_income`` dispatch that gathers coin also gathers gems, and the *same*
outcome band + graft + catastrophe decide what survives. This module is the items-side
seam that dispatch calls (a lazy import from ``currency.services``, keeping the FK
direction — currency stays free of an items dependency at module load).

Landing: net common value → the house's shared ``OrgGemStock`` (the stock members craft
from); surviving Rare-Find stones → the collector's hands; a bad collection loses some.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.items.gems.models import (
    OrgGemStock,
    PendingRareFind,
    StreamCommonGemPool,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import MaterialCategory
    from world.societies.models import Organization


@dataclass(frozen=True)
class GemCollectionResult:
    """What one collection dispatch did to an org's pending gems.

    ``common_value_landed`` is the net common value that reached the house stock (after
    the same band + graft the coin rode); ``stones_delivered`` / ``stones_lost`` count the
    Rare-Find instances that made it to the collector versus those a bad collection ate.
    """

    common_value_landed: int
    stones_delivered: int
    stones_lost: int


def credit_org_gems(
    *, organization: Organization, tier: MaterialCategory, value: int
) -> OrgGemStock:
    """Add ``value`` common-gem coppers to the house's collected stock for ``tier``.

    Mutate-then-save (SharedMemoryModel identity map — never ``F()`` + ``update``).
    """
    stock, _ = OrgGemStock.objects.get_or_create(organization=organization, tier=tier)
    stock.value += value
    stock.save(update_fields=["value"])
    return stock


def org_has_pending_gems(organization: Organization) -> bool:
    """Cheap existence gate: does the org have any uncollected gems on an active stream.

    Lets ``collect_org_income`` proceed for a mine that has accrued gems but no coin — its
    stream's ``uncollected_pool`` is zero yet the gem pools are not.
    """
    return (
        StreamCommonGemPool.objects.filter(
            income_stream__organization=organization,
            income_stream__active=True,
            uncollected_value__gt=0,
        ).exists()
        or PendingRareFind.objects.filter(
            income_stream__organization=organization,
            income_stream__active=True,
        ).exists()
    )


def collect_org_gems(
    *,
    organization: Organization,
    collector_sheet: CharacterSheet,
    band_pct: int | None,
    graft_pct: int,
) -> GemCollectionResult:
    """Gather + zero the org's pending gems and land what the band/graft/catastrophe allow.

    Called inside ``collect_org_income``'s atomic block. The pools zero the moment the
    attempt happens (the gems left with the collector), exactly like the coin. ``band_pct``
    is ``None`` on catastrophe — everything is lost. Otherwise net common value is credited
    to ``OrgGemStock`` per tier, and ``floor(count × band × (1 − graft))`` of the stones
    survive into ``collector_sheet``'s hands (the rest are destroyed).
    """
    # Gather + zero the common-gem pools, aggregating per tier.
    pools = list(
        StreamCommonGemPool.objects.filter(
            income_stream__organization=organization,
            income_stream__active=True,
            uncollected_value__gt=0,
        ).select_related("tier")
    )
    per_tier: dict[int, list] = {}
    for pool in pools:
        entry = per_tier.setdefault(pool.tier_id, [pool.tier, 0])
        entry[1] += pool.uncollected_value
        pool.uncollected_value = 0
        pool.save(update_fields=["uncollected_value"])

    # Gather the pending stones and resolve their pending links (collected now).
    pendings = list(
        PendingRareFind.objects.filter(
            income_stream__organization=organization,
            income_stream__active=True,
        ).select_related("gem_instance")
    )
    stones = [pending.gem_instance for pending in pendings]
    PendingRareFind.objects.filter(pk__in=[pending.pk for pending in pendings]).delete()

    if band_pct is None:
        # Catastrophe: the collector never made it back — common value and stones alike lost.
        for stone in stones:
            stone.delete()
        return GemCollectionResult(
            common_value_landed=0, stones_delivered=0, stones_lost=len(stones)
        )

    common_landed = 0
    for tier, gathered in per_tier.values():
        collected = gathered * band_pct // 100
        net = collected - collected * graft_pct // 100
        if net > 0:
            credit_org_gems(organization=organization, tier=tier, value=net)
            common_landed += net

    # Stones ride the same net rate as coin: band scales, graft eats its cut.
    surviving = len(stones) * band_pct * (100 - graft_pct) // 10000
    survivors, losers = stones[:surviving], stones[surviving:]
    if survivors:
        # #2540 ruling: collection is a mission with a return leg. Each delivered stone
        # is owed to the house vault — mint an in-transit custody row alongside the
        # physical delivery; resolve_vault_transit completes (or embezzles) it.
        from world.items.org_vault_models import VaultTransit  # noqa: PLC0415
        from world.items.services.org_vault import get_or_create_org_vault  # noqa: PLC0415

        vault = get_or_create_org_vault(organization)
        for stone in survivors:
            stone.holder_character_sheet = collector_sheet
            stone.save(update_fields=["holder_character_sheet"])
            VaultTransit.objects.create(
                vault=vault, item_instance=stone, carrier_character_sheet=collector_sheet
            )
    for stone in losers:
        stone.delete()
    return GemCollectionResult(
        common_value_landed=common_landed,
        stones_delivered=len(survivors),
        stones_lost=len(losers),
    )
