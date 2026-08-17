"""Workbench deep-link building, shared by every stock-admin surface (#3020).

Promoted from ``content_row_export_views._workbench_url`` (#3018) so the
credit-status changelist cell, the change-form object-tool link, and the
row-export fallbacks all build the same URL the same way.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import admin
from django.urls import NoReverseMatch, reverse

from core.app_domains import resolve_model_by_name


def workbench_editor_url(model_label: str, pk: object) -> str:
    """Build the Authoring Workbench editor deep-link for one row.

    Unlike a per-model admin change-form URL, this always resolves -
    ``admin_authoring_editor`` is a fixed route, not one built off the admin
    registry (#3019 review, Item 2).
    """
    query = urlencode({"model": model_label, "pk": pk})
    return f"{reverse('admin_authoring_editor')}?{query}"


def admin_change_url(model_label: str, pk: object) -> str | None:
    """Stock-admin change-form link for one row, or ``None`` when it has no ``ModelAdmin``.

    The inverse of ``workbench_editor_url``: the workbench editor only ever
    exposes a row's prose fields, so this is the link an author follows to
    reach everything else on the row (sort orders, flags, foreign keys).

    Not every credited model has a registered ``ModelAdmin`` - three
    (``NPCRole``, ``BuildingKind``, ``DecorationKind``) were never
    ``@admin.register``ed - so checking ``admin.site._registry`` first keeps
    an unregistered model from ever reaching ``reverse()``. The
    ``NoReverseMatch`` catch is defense in depth for any other reason
    ``admin:<app_label>_<model_name>_change`` might not resolve. Callers
    render nothing for ``None`` rather than a dead link.

    Promoted here from ``authoring.views._admin_change_url`` so the
    related-entries pane and the backlog queue build the same URL the same
    way - the ``(model_label, pk)`` signature both ``RelatedEntry`` and
    ``BacklogRow`` can satisfy, since neither carries the model class itself.
    """
    try:
        model = resolve_model_by_name(model_label)
    except LookupError:
        return None
    if model not in admin.site._registry:  # noqa: SLF001
        return None
    app_label = model._meta.app_label  # noqa: SLF001
    model_name = model._meta.model_name  # noqa: SLF001
    try:
        return reverse(f"admin:{app_label}_{model_name}_change", args=[pk])
    except NoReverseMatch:
        return None
