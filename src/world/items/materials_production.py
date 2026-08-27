"""General per-holding material production — the weekly-cron entry point (#2540 slice 2).

Generalizes the Build 0b gem-mine-only ``accrue_mine_cycle`` (deleted; see
``world.items.gems.mining``) to every ``HoldingMaterialSource`` a holding carries, of
either kind:

- GEM_MINE → the gem engine (``roll_gem_haul``, unchanged) rolls a flat common value
  plus, rarely, individuated Rare-Find ``ItemInstance``s.
- BULK → a flat ``quality * BULK_YIELD_PER_QUALITY`` common value, no rare finds.

Both credit the holding's stream's per-category ``StreamMaterialPool``; GEM_MINE rare
finds also become ``PendingRareFind`` rows. Everything sits uncollected until an active
collection dispatch (``collect_org_income``) delivers it with the same graft/loss the
coin pool rides (ADR-0081 — automatic loss is fine, automatic gain is not). Lives
alongside ``materials_models`` rather than in ``gems.mining`` because it is no longer
gem-specific — it imports the gem roller as one of two source-kind branches, not the
other way around.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from world.items.constants import BULK_YIELD_PER_QUALITY, MaterialSourceKind
from world.items.gems.mining import Rng, _d100, roll_gem_haul
from world.items.gems.models import PendingRareFind
from world.items.materials_models import StreamMaterialPool

if TYPE_CHECKING:
    from world.currency.models import OrgIncomeStream
    from world.items.models import ItemInstance, MaterialCategory
    from world.societies.houses.models import DomainHolding


@dataclass(frozen=True)
class MaterialHaul:
    """One weekly cycle's output across every material source on a holding.

    Generalizes ``GemHaul`` (`world.items.gems.mining`) to a holding that may carry
    more than one ``HoldingMaterialSource`` row: one ``(MaterialCategory,
    common_value)`` tuple per source (BULK sources are flat value; GEM_MINE sources
    fold in ``roll_gem_haul``'s common value) plus every GEM_MINE source's rare finds
    pooled together.
    """

    common_value_by_category: list[tuple[MaterialCategory, int]]
    rare_finds: list[ItemInstance]


def _credit_stream_pool(
    *, stream: OrgIncomeStream, material_category: MaterialCategory, value: int
) -> None:
    """Accrue ``value`` into the stream's uncollected pool for ``material_category``."""
    pool, created = StreamMaterialPool.objects.get_or_create(
        income_stream=stream,
        material_category=material_category,
        defaults={"uncollected_value": value},
    )
    if not created:
        pool.uncollected_value += value
        pool.save(update_fields=["uncollected_value"])


def accrue_holding_materials(
    *,
    holding: DomainHolding,
    minister_bonus: int = 0,
    roll: Rng = _d100,
) -> MaterialHaul:
    """Run one weekly cycle for every material source on ``holding``.

    Replaces the Build 0b gem-mine-only ``accrue_mine_cycle`` (deleted, #2540 Task 2):
    a holding may carry any mix of BULK and GEM_MINE ``HoldingMaterialSource`` rows,
    and each accrues into the stream's per-category ``StreamMaterialPool`` the same
    way. GEM_MINE sources also roll rare finds via ``roll_gem_haul`` (``minister_bonus``
    passed through — the schema-only #2239 minister-check seam applies to gem mines
    only, mirroring the prior interim behavior); BULK sources produce a flat
    ``quality * BULK_YIELD_PER_QUALITY`` value only. A holding with no income stream
    accrues nothing (mirrors the old guard) — a holding with no material sources at
    all likewise accrues nothing (the weekly caller filters these out first, but the
    guard holds either way).
    """
    stream = holding.income_stream
    if stream is None:
        return MaterialHaul(common_value_by_category=[], rare_finds=[])

    common_value_by_category: list[tuple[MaterialCategory, int]] = []
    rare_finds: list[ItemInstance] = []
    with transaction.atomic():
        for source in holding.material_sources.select_related("material_category"):
            category = source.material_category
            if source.source_kind == MaterialSourceKind.GEM_MINE:
                gem_haul = roll_gem_haul(
                    mine_quality=source.quality, minister_bonus=minister_bonus, roll=roll
                )
                common_value = gem_haul.common_value
                rare_finds.extend(gem_haul.rare_finds)
            else:
                common_value = source.quality * BULK_YIELD_PER_QUALITY
            common_value_by_category.append((category, common_value))
            if common_value > 0:
                _credit_stream_pool(stream=stream, material_category=category, value=common_value)
        for gem in rare_finds:
            PendingRareFind.objects.create(income_stream=stream, gem_instance=gem)
    return MaterialHaul(common_value_by_category=common_value_by_category, rare_finds=rare_finds)
