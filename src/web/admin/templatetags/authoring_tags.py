"""Template filters for the Authoring Workbench and its cross-links (#3020, #3675 Task 10).

``change_form.html`` needs one value: the workbench editor URL for the row on
screen, or ``""`` when there is nothing to link (non-credited model, credited
model with no prose fields, or an unsaved add-form object). Kept separate
from ``content_export_tags`` - that module is the #3018 export button's and
answers a different question (corpus-owned) than this one (prose-editable).
"""

from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

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


@register.simple_tag
def builder_link(obj: object) -> SafeString | str:
    """Render `<a href="...">label</a>` to ``obj``'s own Builder page (#3675 Task 10).

    A thin template wrapper over `web.admin.authoring.links.builder_url`/
    `builder_label` - "" (no anchor at all) for an object with no Builder
    page of its own, the same objects those two functions already return ""
    for. Used by the tradition slate page's "Carries"/"Grants" cells to link
    a Distinction back to the Distinction Builder.
    """
    from web.admin.authoring.links import builder_label, builder_url  # noqa: PLC0415

    url = builder_url(obj)
    if not url:
        return ""
    return format_html('<a href="{}">{}</a>', url, builder_label(obj))
