"""Typed shapes for creation-time technique personalization (#4099)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import Restriction, SignatureMotifBonus, Technique
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


@dataclass(frozen=True)
class PricedPersonalizationLine:
    """One CG-points breakdown line for one pick."""

    technique_name: str
    option_name: str
    cost: int
