"""Template filters for the change-form "Export to content repo" button (#3018).

``web/templates/admin/change_form.html`` needs to know two things about the
object currently on screen: whether its model is corpus-owned at all
(``content_exportable``) and, if so, the ``<domain>.<model_name>`` label the
row-export POST view (``admin_content_export_row``) expects in its hidden
``model`` field (``content_model_label``). Both filters compute the same
label the same way ``content_row_export_views._resolve_model_and_instance``
resolves it back from, via ``core.app_domains.resolve_model_by_name``.
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def content_exportable(obj) -> bool:
    """True when this admin object's model is corpus-owned (#3018).

    ``obj`` is always either ``None`` or a Django model instance here (the
    caller is always ``change_form.html``'s ``original`` context variable),
    so ``obj.pk`` is safe once the ``None`` case is ruled out by the
    short-circuiting ``or`` below.
    """
    if obj is None or not obj.pk:
        return False
    from core.app_domains import domain_of  # noqa: PLC0415
    from core_management.content_export import CONTENT_MODELS  # noqa: PLC0415
    from core_management.content_fixtures import MARKDOWN_EXPORT_DOMAINS  # noqa: PLC0415

    label = f"{domain_of(type(obj))}.{type(obj).__name__.lower()}"
    return label in CONTENT_MODELS or label in MARKDOWN_EXPORT_DOMAINS


@register.filter
def content_model_label(obj) -> str:
    """Return this admin object's ``<domain>.<model_name>`` row-export label (#3018)."""
    from core.app_domains import domain_of  # noqa: PLC0415

    return f"{domain_of(type(obj))}.{type(obj).__name__.lower()}"
