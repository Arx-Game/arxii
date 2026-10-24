"""Putting the identity map back after a refused builder save.

Validating a ``ModelForm`` writes the posted values onto ``form.instance`` (Django's
``_post_clean``), and for a saved row that instance is the one SharedMemoryModel's
identity map hands to every later reader in the process. A refused save would leave the
refused values there: the next page load shows them as if saved, and the corrected
save compares against them, finds no change for that row and skips the write while
reporting success. Render the errors first (they need the posted values), then call
``flush_refused_instances`` so the next reader loads what the database holds.

A page that assigns posted values onto a row itself, outside any form, and then calls
``full_clean()`` (the authoring workbench's row editor, #4543) has the same hazard and
passes the row directly.

A stock Django admin change page has the same hazard on every refused save, for its own
form and every inline formset; ``RefusedSaveFlushMixin`` gives a ``ModelAdmin`` that
protection (``TechniqueAdmin`` uses it, #4619).
"""

from __future__ import annotations

from django.forms import BaseModelForm, BaseModelFormSet
from django.template.response import TemplateResponse
from evennia.utils.idmapper.models import SharedMemoryModel


def flush_refused_instances(*bound: BaseModelForm | BaseModelFormSet | SharedMemoryModel) -> None:
    """Drop every saved row behind these bound forms, formsets or rows from the identity map.

    A row passed directly is one the caller assigned posted values onto before a refused
    ``full_clean()``. An unsaved row (no pk) was never cached, so it is skipped.
    """
    for item in bound:
        if isinstance(item, SharedMemoryModel):
            instances = [item]
        elif isinstance(item, BaseModelFormSet):
            instances = [form.instance for form in item.forms]
        else:
            instances = [item.instance]
        for instance in instances:
            if instance.pk is not None:
                instance.flush_from_cache(force=True)


class RefusedSaveFlushMixin:
    """A ``ModelAdmin`` mixin: a refused change-page save leaves the identity map as stored.

    Django's ``_changeform_view`` validates the change form and every inline formset on a
    POST, which writes the posted values onto the cached rows behind them. A valid save
    redirects; ``render_change_form`` is only reached on a POST when the save was refused
    (a GET reaches it too, and nothing was bound then). On that path this renders the
    errors page (it shows the posted values), then drops every saved row behind the
    form and the inline formsets, in a ``finally`` so a template error cannot skip it.
    """

    def render_change_form(  # noqa: PLR0913 - ModelAdmin.render_change_form's own signature
        self, request, context, add=False, change=False, form_url="", obj=None
    ) -> TemplateResponse:
        response = super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )
        if request.method != "POST":
            return response
        bound = [
            context["adminform"].form,
            *(inline.formset for inline in context["inline_admin_formsets"]),
        ]
        try:
            response.render()
        finally:
            flush_refused_instances(*bound)
        return response
