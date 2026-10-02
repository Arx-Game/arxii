"""Typed shapes for creation-time technique personalization (#4099)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.models import ItemInstance
    from world.magic.models import (
        PriceComponentRequirement,
        Restriction,
        SignatureMotifBonus,
        Technique,
    )
    from world.magic.specialization.models import TechniqueVariant


@dataclass(frozen=True)
class TechniquePersonalizationPick:
    """One technique's creation picks, parsed from the draft."""

    technique_id: int
    custom_name: str = ""
    custom_description: str = ""
    signature_bonus_id: int | None = None
    early_form_id: int | None = None
    price_id: int | None = None


@dataclass(frozen=True)
class PersonalizationOptionSet:
    """What creation offers for one chosen technique at the draft's gift resonance."""

    technique: Technique
    flourishes: list[SignatureMotifBonus] = field(default_factory=list)
    forms: list[TechniqueVariant] = field(default_factory=list)
    prices: list[Restriction] = field(default_factory=list)
    #: Each offered price's consumed components, keyed by price pk (one bulk read).
    price_components: Mapping[int, list[PriceComponentRequirement]] = field(default_factory=dict)


@dataclass(frozen=True)
class PricedPersonalizationLine:
    """One CG-points breakdown line for one pick."""

    technique_name: str
    option_name: str
    cost: int


@dataclass(frozen=True)
class PricePayment:
    """The one decision that a cast pays its caster's price (#4099, ADR-4099).

    Made once per cast by ``price_paid_for_cast``. The power term, the narration
    clause, the component consumption and the inflicted condition all read this
    object, so they can never disagree. ``allocations`` are the carried
    ``(ItemInstance, amount)`` pairs the cast will consume when it resolves.
    """

    price: Restriction
    allocations: tuple[tuple[ItemInstance, int], ...] = ()
