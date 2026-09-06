"""Template helpers for the Upbringing Builder (#3660).

``builder_url`` backs the change-form "Open in Upbringing Builder" object
tool, mirroring ``authoring_tags.workbench_url``. ``dict_get`` is the page's
own lookup helper: ``live.groups_by_slot`` and the per-slot answers formsets
are both keyed by a slot's pk, and Django's template variable resolution only
supports a literal dict key written into the template, never one held in
another context variable - so looking either dict up by
``question_form.instance.pk`` needs this filter.
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def builder_url(obj) -> str:
    from django.urls import reverse  # noqa: PLC0415

    from world.character_creation.models import OriginTemplate  # noqa: PLC0415

    if not isinstance(obj, OriginTemplate) or not obj.pk:
        return ""
    return reverse("admin_upbringing_builder", args=[obj.pk])


@register.filter
def dict_get(mapping: dict | None, key) -> object:
    """``mapping.get(key)``, or ``None`` when ``mapping`` itself is falsy."""
    if not mapping:
        return None
    return mapping.get(key)
