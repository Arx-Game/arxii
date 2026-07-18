"""Gem worth computation + adornment (Build 0b slices 1-2)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.items.exceptions import (
    AdornmentCapacityExceeded,
    GemAlreadyAdorned,
    NotAGem,
)
from world.items.gems.models import Adornment

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

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
