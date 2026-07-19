"""Gem worth computation, adornment, risky prying, and cutting (Build 0b slices 1-2, 3, 6)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.checks.services import perform_check
from world.items.exceptions import (
    AdornmentCapacityExceeded,
    CraftingCostUnaffordable,
    CraftingNotConfigured,
    GemAlreadyAdorned,
    NotAGem,
)
from world.items.gems.constants import GemAxis
from world.items.gems.models import Adornment, GemGrade

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.items.crafting.models import CraftingRecipe
    from world.items.gems.models import GemInstanceDetails
    from world.items.models import ItemInstance, ItemTemplate


def compute_gem_worth(gem: GemInstanceDetails) -> int:
    """Return a gem's worth in coppers: ``template.value × size × purity × cut``.

    The base value comes from the gem *type* (``ItemTemplate.value``, set by the
    type's quality level); the three grade multipliers scale it. Rounded to a whole
    copper. Consumed by ``world.items.services.pricing.appraise`` for gem instances.
    """
    base = gem.item_instance.template.value
    factor = (
        Decimal(str(gem.size_grade.multiplier))
        * Decimal(str(gem.purity_grade.multiplier))
        * Decimal(str(gem.cut_grade.multiplier))
    )
    return int((Decimal(base) * factor).to_integral_value())


def adorn_item(
    *,
    host_instance: ItemInstance,
    gem_instance: ItemInstance,
    narration: str = "",
    set_by_account: AccountDB | None = None,
) -> Adornment:
    """Set ``gem_instance`` into ``host_instance`` as adornment (Build 0b, safe path).

    Raises ``NotAGem`` if the offered instance is not a gem, ``GemAlreadyAdorned`` if
    it is already set somewhere, or ``AdornmentCapacityExceeded`` if the host is full.
    On success: creates the ``Adornment`` (keeping the gem's identity/provenance inside
    the piece), embeds the gem (clears its holder — it's now in the piece, not carried),
    and adds the gem's worth to the host's ``lore_value`` so the wired ``appraise()``
    reflects it. This is the craft-time / safe adorning path; risky re-setting (prying
    a gem back out) is a later, check-gated slice.
    """
    gem = gem_instance.gem_or_none
    if gem is None:
        raise NotAGem
    if Adornment.objects.filter(gem_instance=gem_instance).exists():
        raise GemAlreadyAdorned
    if host_instance.adornments.count() >= host_instance.template.adornment_capacity:
        raise AdornmentCapacityExceeded

    with transaction.atomic():
        adornment = Adornment.objects.create(
            host_instance=host_instance,
            gem_instance=gem_instance,
            narration=narration,
            set_by_account=set_by_account,
        )
        gem_instance.holder_character_sheet = None
        gem_instance.save(update_fields=["holder_character_sheet"])
        host_instance.lore_value = (host_instance.lore_value or 0) + compute_gem_worth(gem)
        host_instance.save(update_fields=["lore_value"])
    return adornment


def adorned_materials(host_instance: ItemInstance) -> list[ItemTemplate]:
    """The gem types set into ``host_instance`` — the queryable "materials on this piece".

    The seam the magic app reads to answer "does this piece carry a ruby (or any
    precious-tier material)". Each returned template is a gem type; its
    ``material_category`` is its tier and its ``tied_resonance`` its motif.
    """
    return [
        adornment.gem_instance.template
        for adornment in host_instance.adornments.select_related("gem_instance__template")
    ]


@dataclass(frozen=True)
class PryResult:
    """Outcome of a ``pry_adornment`` attempt.

    The gem leaves the piece either way (so ``worth_removed`` always drops from the
    host). On success ``freed_gem`` is the stone, returned to the pryer's inventory;
    on a botch the stone shatters (``shattered=True``, ``freed_gem=None``).
    """

    shattered: bool
    freed_gem: ItemInstance | None
    worth_removed: int


def pry_adornment(  # noqa: PLR0913 — keyword-only adornment + crafter + check-config params
    *,
    adornment: Adornment,
    crafter_character: ObjectDB,
    crafter_character_sheet: CharacterSheet,
    check_type: CheckType,
    base_difficulty: int = 0,
    min_success_level: int = 1,
    ap_cost: int = 0,
) -> PryResult:
    """Attempt to pry a set gem out of its piece — the risky end of the adornment lifecycle.

    Reuses ``perform_check`` (skill feeds the roll). The gem *leaves the piece regardless*
    of outcome, so the host's ``lore_value`` drops by the gem's worth. On success the gem
    is **freed** to the pryer's inventory; on a botch it **shatters** (destroyed). Spends
    the ``ap_cost`` up front. Same high-risk/high-reward spine as gem cutting.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    gem_instance = adornment.gem_instance
    host = adornment.host_instance
    worth = compute_gem_worth(gem_instance.gem_or_none)

    if ap_cost > 0:
        pool = ActionPointPool.get_or_create_for_character(crafter_character)
        if not pool.spend(ap_cost):
            msg = f"You need {ap_cost} action points but only have {pool.current}."
            raise CraftingCostUnaffordable(msg)

    with transaction.atomic():
        host.lore_value = max(0, (host.lore_value or 0) - worth)
        host.save(update_fields=["lore_value"])

        check_result = perform_check(crafter_character, check_type, base_difficulty)
        if check_result.success_level < min_success_level:
            gem_instance.delete()  # CASCADE removes the Adornment + GemInstanceDetails
            return PryResult(shattered=True, freed_gem=None, worth_removed=worth)

        adornment.delete()  # remove the setting; the stone survives
        gem_instance.holder_character_sheet = crafter_character_sheet
        gem_instance.save(update_fields=["holder_character_sheet"])
        return PryResult(shattered=False, freed_gem=gem_instance, worth_removed=worth)


@dataclass(frozen=True)
class CutResult:
    """Outcome of a ``cut_gem`` attempt.

    On a botch the stone shatters (``shattered=True``, gem instance deleted); the
    forfeited worth is reported in ``worth_lost``. On success the cut grade improves
    and ``worth`` is the gem's new worth.
    """

    shattered: bool
    new_cut_grade: GemGrade | None
    worth: int
    worth_lost: int


def resolve_cut_grade(current_cut: GemGrade, success_level: int) -> GemGrade:
    """Return the cut grade a successful cut reaches from ``current_cut``.

    Advances up the CUT-axis grade ladder by ``success_level`` positions (a better
    roll = a finer cut), capped at the top grade and never below the current grade.
    Skill therefore gates the achievable cut through the check outcome (a hard,
    skill-value cap à la ``CraftingSkillCap`` is a deferred refinement).
    """
    cuts = list(GemGrade.objects.filter(axis=GemAxis.CUT).order_by("sort_order"))
    current_index = cuts.index(current_cut)
    target_index = min(current_index + max(success_level, 1), len(cuts) - 1)
    return cuts[target_index]


def cut_gem(
    *,
    gem_instance: ItemInstance,
    crafter_character: ObjectDB,
    recipe: CraftingRecipe,
) -> CutResult:
    """Attempt to cut/improve a gem via ``recipe`` (a ``GEM_CUT`` CraftingRecipe).

    Reuses the crafting config + ``perform_check`` (the crafter's ``skill_trait`` feeds
    the roll). Spends the recipe's AP cost up front. On success
    (``success_level >= recipe.min_success_level``) the cut grade improves and worth
    rises; on a botch the stone **shatters** (deleted). Raises ``NotAGem`` if the
    instance is not a gem, ``CraftingNotConfigured`` if the recipe has no check, or
    ``CraftingCostUnaffordable`` if the crafter can't pay the AP.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    gem = gem_instance.gem_or_none
    if gem is None:
        raise NotAGem
    if recipe.check_type is None:
        raise CraftingNotConfigured

    ap_cost = recipe.action_point_cost
    if ap_cost > 0:
        pool = ActionPointPool.get_or_create_for_character(crafter_character)
        if not pool.spend(ap_cost):
            msg = f"You need {ap_cost} action points but only have {pool.current}."
            raise CraftingCostUnaffordable(msg)

    check_result = perform_check(crafter_character, recipe.check_type, recipe.base_difficulty)

    if check_result.success_level < recipe.min_success_level:
        worth_lost = compute_gem_worth(gem)
        gem_instance.delete()  # CASCADE deletes GemInstanceDetails
        return CutResult(shattered=True, new_cut_grade=None, worth=0, worth_lost=worth_lost)

    new_cut = resolve_cut_grade(gem.cut_grade, check_result.success_level)
    gem.cut_grade = new_cut
    gem.save(update_fields=["cut_grade"])
    return CutResult(
        shattered=False, new_cut_grade=new_cut, worth=compute_gem_worth(gem), worth_lost=0
    )
