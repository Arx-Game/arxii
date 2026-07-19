"""Gem mining — the weekly haul-generation engine (Build 0b slice 4).

Given a mine's quality and the overseeing minister's bonus, produce a **haul**: a
bulk of common gems expressed as an aggregate *value* (never instanced) plus, rarely,
a few individuated "Rare Find" stones (real ``ItemInstance``s, born uncut).

``roll_gem_haul`` is the pure distribution engine — deterministic when handed an injected
``roll``, so it is fully testable. ``accrue_mine_cycle`` runs one weekly cycle for a mine
holding, accruing the haul into the stream's uncollected gem pools (the gem analogue of
``OrgIncomeStream.uncollected_pool``). What remains for the Build-1 wiring: the *scheduling*
(a game_clock task calling ``accrue_mine_cycle`` weekly), the active *collection* dispatch
(``collect_org_income`` delivering the pools with graft/loss), and the (schema-only, #2239)
minister-check seam.

All magnitudes are PLACEHOLDER (see constants); the *shape* is the deliverable:
multiplicative axes + independent skewed rolls give the fat "remarkable find" tail for
free, and mine quality both raises the Rare-Find chance and shifts every axis roll up.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import random
from typing import TYPE_CHECKING

from django.db import transaction

from world.items.gems.constants import (
    COMMON_VALUE_PER_QUALITY,
    RARE_FIND_BASE_CHANCE,
    RARE_FIND_MAX_COUNT,
    GemAxis,
)
from world.items.gems.models import (
    GemGrade,
    GemInstanceDetails,
    PendingRareFind,
    StreamCommonGemPool,
)
from world.items.models import ItemInstance, ItemTemplate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.societies.houses.models import DomainHolding

# A roll returns a d100 (1-100). Injectable so the engine is deterministic in tests.
Rng = Callable[[], int]


def _d100() -> int:
    return random.randint(1, 100)  # noqa: S311


@dataclass(frozen=True)
class GemHaul:
    """One mine cycle's output: bulk common value + any individuated Rare Finds."""

    common_value: int
    rare_finds: list[ItemInstance]


def _grade_index(effective_roll: int, num_grades: int, floor_index: int) -> int:
    """Map an effective (already mine-boosted) d100 roll to a grade index.

    Top-heavy by design — high grades are genuinely rare (``(roll/100)**2`` scaling), so
    the product of two rare rolls (size × purity) is what makes a legendary stone. Never
    below ``floor_index`` (Rare Finds floor size/purity above the common band); capped at
    the top grade. PLACEHOLDER distribution — the curve is tunable, the *structure* isn't.
    """
    if num_grades <= 1:
        return 0
    clamped = max(1, min(effective_roll, 100))
    span = num_grades - 1 - floor_index
    if span <= 0:
        return min(floor_index, num_grades - 1)
    idx = floor_index + int((clamped / 100) ** 2 * span)
    return max(floor_index, min(idx, num_grades - 1))


def _all_gem_types() -> list[ItemTemplate]:
    """Every gem *type* (an ItemTemplate with a GemDetails sidecar), rarest last."""
    return list(
        ItemTemplate.objects.filter(gem_details__isnull=False).order_by(
            "gem_details__quality_level"
        )
    )


def _mint_raw_gem(
    gem_type: ItemTemplate, size: GemGrade, purity: GemGrade, uncut: GemGrade
) -> ItemInstance:
    """Create a loose, uncut Rare-Find gem instance (holder unset — the caller places it)."""
    instance = ItemInstance.objects.create(template=gem_type)
    GemInstanceDetails.objects.create(
        item_instance=instance, size_grade=size, purity_grade=purity, cut_grade=uncut
    )
    return instance


def roll_gem_haul(
    *,
    mine_quality: int,
    minister_bonus: int = 0,
    type_pool: Sequence[ItemTemplate] | None = None,
    roll: Rng = _d100,
) -> GemHaul:
    """Roll one mine cycle's haul.

    ``mine_quality`` and ``minister_bonus`` both (a) raise the Rare-Find chance and
    (b) add to every axis roll (a +10 mine turns a 90 into a 100 — max for the roll).
    ``type_pool`` limits which gem types this mine can yield (default: all gem types).
    ``roll`` is the injectable d100 source. Common bulk is returned as a value only;
    Rare Finds are minted as loose uncut ``ItemInstance``s with ``size``/``purity``
    floored above the common band (``type`` is not floored — a huge flawless *common*
    stone is a legitimate find).
    """
    quality = max(0, mine_quality)
    boost = quality + max(0, minister_bonus)
    common_value = quality * COMMON_VALUE_PER_QUALITY

    chance = RARE_FIND_BASE_CHANCE + boost
    if roll() > chance:
        return GemHaul(common_value=common_value, rare_finds=[])

    size_grades = list(GemGrade.objects.filter(axis=GemAxis.SIZE).order_by("sort_order"))
    purity_grades = list(GemGrade.objects.filter(axis=GemAxis.PURITY).order_by("sort_order"))
    cut_grades = list(GemGrade.objects.filter(axis=GemAxis.CUT).order_by("sort_order"))
    types = list(type_pool) if type_pool is not None else _all_gem_types()
    if not (size_grades and purity_grades and cut_grades and types):
        # Not enough seeded content to mint a stone — yield the common bulk only.
        return GemHaul(common_value=common_value, rare_finds=[])
    uncut = cut_grades[0]

    count = 1 + (roll() - 1) % RARE_FIND_MAX_COUNT  # 1..RARE_FIND_MAX_COUNT
    finds: list[ItemInstance] = []
    for _ in range(count):
        gem_type = types[_grade_index(roll() + boost, len(types), 0)]  # type: not floored
        size = size_grades[_grade_index(roll() + boost, len(size_grades), 1)]  # floored
        purity = purity_grades[_grade_index(roll() + boost, len(purity_grades), 1)]  # floored
        finds.append(_mint_raw_gem(gem_type, size, purity, uncut))
    return GemHaul(common_value=common_value, rare_finds=finds)


def accrue_mine_cycle(
    *,
    holding: DomainHolding,
    minister_bonus: int = 0,
    roll: Rng = _d100,
) -> GemHaul:
    """Run one weekly cycle for a mine ``holding``, accruing its haul into the uncollected pools.

    Common value amasses in the stream's ``StreamCommonGemPool`` for the holding's
    ``common_gem_tier``; each Rare Find becomes a ``PendingRareFind`` on the stream. Both sit
    uncollected until an active collection dispatch (``collect_org_income``) delivers them with
    the same graft/loss the coin pool rides. A holding with no income stream or no
    ``common_gem_tier`` is not a configured gem mine — nothing accrues.
    """
    stream = holding.income_stream
    tier = holding.common_gem_tier
    if stream is None or tier is None:
        return GemHaul(common_value=0, rare_finds=[])

    haul = roll_gem_haul(
        mine_quality=holding.mine_quality, minister_bonus=minister_bonus, roll=roll
    )
    with transaction.atomic():
        if haul.common_value > 0:
            pool, created = StreamCommonGemPool.objects.get_or_create(
                income_stream=stream,
                tier=tier,
                defaults={"uncollected_value": haul.common_value},
            )
            if not created:
                pool.uncollected_value += haul.common_value
                pool.save(update_fields=["uncollected_value"])
        for gem in haul.rare_finds:
            PendingRareFind.objects.create(income_stream=stream, gem_instance=gem)
    return haul
