"""Template helpers for the Upbringing Builder (#3660).

``builder_url``/``builder_label`` back the change-form "Open in Upbringing
Builder"/"Open the tradition slate" object tool, mirroring
``authoring_tags.workbench_url`` - both now delegate to
``web.admin.authoring.links`` (#3675), which knows every model with a
builder-style page, not just this one. ``dict_get`` is the page's own lookup
helper: ``live.groups_by_slot`` and the per-slot answers formsets are both
keyed by a slot's pk, and Django's template variable resolution only
supports a literal dict key written into the template, never one held in
another context variable - so looking either dict up by
``question_form.instance.pk`` needs this filter.

``upbringing_fieldsets`` and ``question_fieldsets`` wrap a form so the page
can draw it through Django admin's own ``admin/includes/fieldset.html``
(#3667).
"""

from __future__ import annotations

from django import template
from django.contrib.admin.helpers import AdminForm

from web.admin.upbringing_builder.forms import QUESTION_FIELDSETS, UPBRINGING_FIELDSETS

register = template.Library()


@register.filter
def builder_url(obj) -> str:
    from web.admin.authoring.links import builder_url as _builder_url  # noqa: PLC0415

    return _builder_url(obj)


@register.filter
def builder_label(obj) -> str:
    from web.admin.authoring.links import builder_label as _builder_label  # noqa: PLC0415

    return _builder_label(obj)


@register.filter
def dict_get(mapping: dict | None, key) -> object:
    """``mapping.get(key)``, or ``None`` when ``mapping`` itself is falsy."""
    if not mapping:
        return None
    return mapping.get(key)


@register.filter
def upbringing_fieldsets(form) -> AdminForm:
    """The Upbringing form, wrapped so ``admin/includes/fieldset.html`` can render it.

    The Builder is a custom admin page, so it draws its fields through admin's
    own fieldset template rather than a hand-written layout: that is where the
    label column, the help lines, the checkbox rows, the required markers and
    the per-field error markup come from, and the reason #3660's
    ``{{ form.as_div }}`` rendered unstyled (#3667). Wrapping happens here
    rather than in the view because the questions formset is iterated in the
    template, and its empty form needs the same treatment.
    """
    return AdminForm(form, UPBRINGING_FIELDSETS, {})


@register.filter
def question_fieldsets(form) -> AdminForm:
    """One question's form, wrapped for ``admin/includes/fieldset.html``."""
    return AdminForm(form, QUESTION_FIELDSETS, {})
