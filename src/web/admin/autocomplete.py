"""Autocomplete results that honour the requesting admin's own field queryset (#4089).

Django's autocomplete view filters a related admin's results by the source
field's ``limit_choices_to`` only, never by the queryset the source admin's
``formfield_for_foreignkey`` narrows the field to. A remote admin calls
``source_field_queryset`` from its ``get_search_results`` so a narrowed picker
offers what its form will accept, without the remote app knowing who narrowed it.
"""

from __future__ import annotations

from django import forms
from django.apps import apps
from django.contrib.admin import AdminSite
from django.core.exceptions import FieldDoesNotExist
from django.db.models import QuerySet
from django.http import HttpRequest


def source_field_queryset(request: HttpRequest, admin_site: AdminSite) -> QuerySet | None:
    """The queryset the requesting admin's own formfield offers, or None when there is none.

    Reads the autocomplete view's own ``app_label``/``model_name``/``field_name``
    params. ``None`` for any request that is not an autocomplete from a registered
    admin's foreign key.
    """
    app_label = request.GET.get("app_label")
    model_name = request.GET.get("model_name")
    field_name = request.GET.get("field_name")
    if not (app_label and model_name and field_name):
        return None
    try:
        source_model = apps.get_model(app_label, model_name)
        db_field = source_model._meta.get_field(field_name)  # noqa: SLF001
    except (LookupError, FieldDoesNotExist):
        return None
    source_admin = admin_site._registry.get(source_model)  # noqa: SLF001
    if source_admin is None or not db_field.many_to_one:
        return None
    formfield = source_admin.formfield_for_foreignkey(db_field, request)
    if not isinstance(formfield, forms.ModelChoiceField):
        return None
    return formfield.queryset
