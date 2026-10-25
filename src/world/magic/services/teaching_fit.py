"""Tradition teaching fit (slice 2 of #4659)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.magic.constants import GiftKind
from world.magic.models import (
    Affinity,
    CharacterGift,
    Gift,
    Resonance,
    Tradition,
    TraditionGiftGrant,
    TraditionTeachingConfig,
)
from world.magic.types.teaching_fit import TeachingFit

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def get_teaching_config() -> TraditionTeachingConfig:
    """Lazily create and return the singleton TraditionTeachingConfig (pk=1)."""
    config = TraditionTeachingConfig.objects.cached_singleton()
    if config is None:
        config, _ = TraditionTeachingConfig.objects.get_or_create(pk=1)
    return config


def teaching_fit(
    tradition: Tradition | None,
    gift: Gift | None,
    aura_type: str | None,
) -> TeachingFit:
    """Resolve how well ``tradition`` teaches ``gift`` to someone of ``aura_type``.

    Gift fit: a TraditionGiftGrant(tradition, gift) exists. Affinity fit: one of the
    Tradition's favored Affinities carries this ``aura_type`` (matched by the field,
    never by name; a blank aura_type never fits).
    """
    if tradition is None:
        return TeachingFit(None, False, False, None, None)
    gift_name = None
    if (
        gift is not None
        and TraditionGiftGrant.objects.filter(tradition=tradition, gift=gift).exists()
    ):
        gift_name = gift.name
    affinity_name = None
    if aura_type:
        affinity = Affinity.objects.filter(
            favoring_traditions=tradition, aura_type=aura_type
        ).first()
        if affinity is not None:
            affinity_name = affinity.name
    return TeachingFit(
        tradition=tradition,
        gift_fit=gift_name is not None,
        affinity_fit=affinity_name is not None,
        favored_gift_name=gift_name,
        favored_affinity_name=affinity_name,
    )


def cg_aura_type(resonance: Resonance | None) -> str | None:
    """The aura type of a resonance's affinity, None when unset or blank."""
    if resonance is None:
        return None
    return resonance.affinity.aura_type or None


def character_aura_type(sheet: CharacterSheet) -> str | None:
    """The sheet's dominant aura type, None when it has no aura row."""
    try:
        return str(sheet.aura.dominant_affinity.value)
    except ObjectDoesNotExist:
        return None


def major_gift_for(sheet: CharacterSheet) -> Gift | None:
    """The sheet's Major Gift (the CharacterGift whose Gift is MAJOR), None when it has none."""
    row = (
        CharacterGift.objects.filter(character=sheet, gift__kind=GiftKind.MAJOR)
        .select_related("gift")
        .order_by("pk")
        .first()
    )
    return row.gift if row is not None else None
