"""Template filter for the change-form "Open in Authoring Workbench" link (#3020).

``change_form.html`` needs one value: the workbench editor URL for the row on
screen, or ``""`` when there is nothing to link (non-credited model, credited
model with no prose fields, or an unsaved add-form object). Kept separate
from ``content_export_tags`` - that module is the #3018 export button's and
answers a different question (corpus-owned) than this one (prose-editable).
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def workbench_url(obj) -> str:
    """Return the workbench editor deep-link for this row, or ``""`` when it has none."""
    if obj is None or not obj.pk:
        return ""
    from core.app_domains import credited_content_models, domain_of  # noqa: PLC0415
    from core_management.prose_fields import prose_fields_for  # noqa: PLC0415
    from web.admin.authoring.links import workbench_editor_url  # noqa: PLC0415

    model = type(obj)
    if model not in credited_content_models() or not prose_fields_for(model):
        return ""
    return workbench_editor_url(f"{domain_of(model)}.{model.__name__}", obj.pk)
