"""Template helpers for the Distinction Builder (#3675)."""

from __future__ import annotations

from django import template

from world.character_creation.models import DistinctionOffer
from world.distinctions.models import DistinctionEffect

register = template.Library()


@register.filter
def effect_reads(effect: DistinctionEffect | None) -> str:
    """The player-facing gloss for one saved ``DistinctionEffect`` row.

    "" for an unsaved row (a blank ``extra`` form has no ``target`` yet, and
    ``live.effect_reads`` needs one) - the template only shows this cell once
    a row is saved anyway.
    """
    from web.admin.distinction_builder import live  # noqa: PLC0415

    if effect is None or not effect.pk or not effect.target_id:
        return ""
    return live.effect_reads(effect)


@register.filter
def opener_link(offer: DistinctionOffer | None, default_slate_url: str) -> str:
    """The "Opened by" cell's own link for one saved ``DistinctionOffer`` row (#3675 Task 10).

    "" for an unsaved row - a blank ``extra`` form has no opener set yet.
    """
    from web.admin.distinction_builder import live  # noqa: PLC0415

    if offer is None or not offer.pk:
        return ""
    return live.opener_link(offer, default_slate_url=default_slate_url)
