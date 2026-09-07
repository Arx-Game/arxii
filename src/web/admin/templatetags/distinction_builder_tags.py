"""Template helpers for the Distinction Builder (#3675)."""

from __future__ import annotations

from django import template

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
