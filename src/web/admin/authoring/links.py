"""Workbench deep-link building, shared by every stock-admin surface (#3020).

Promoted from ``content_row_export_views._workbench_url`` (#3018) so the
credit-status changelist cell, the change-form object-tool link, and the
row-export fallbacks all build the same URL the same way.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse


def workbench_editor_url(model_label: str, pk: object) -> str:
    """Build the Authoring Workbench editor deep-link for one row.

    Unlike a per-model admin change-form URL, this always resolves -
    ``admin_authoring_editor`` is a fixed route, not one built off the admin
    registry (#3019 review, Item 2).
    """
    query = urlencode({"model": model_label, "pk": pk})
    return f"{reverse('admin_authoring_editor')}?{query}"
