"""Workbench deep-link building, shared by every stock-admin surface (#3020).

Promoted from ``content_row_export_views._workbench_url`` (#3018) so the
credit-status changelist cell, the change-form object-tool link, and the
row-export fallbacks all build the same URL the same way.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import admin
from django.db.models import Model
from django.urls import NoReverseMatch, reverse

from core.app_domains import resolve_model_by_name
from world.character_creation.models import Beginnings, OriginTemplate
from world.combat.models import CreatureTemplate
from world.conditions.models import ConditionStage
from world.distinctions.models import Distinction
from world.magic.services.soulfray import is_soulfray_stage
from world.missions.models import MissionOptionOpponentLine
from world.societies.models import Organization, Society
from world.worship.models import WorshippedBeing

#: Model -> the custom page that edits one of its rows (a Soulfray ConditionStage is the
#: one conditional case and is handled in ``builder_url``).
_BUILDER_ROUTES: tuple[tuple[type[Model], str], ...] = (
    (OriginTemplate, "admin_upbringing_builder"),
    (Beginnings, "admin_tradition_slate"),
    (Distinction, "admin_distinction_builder"),
    (CreatureTemplate, "admin_standoff_profile"),
    (Organization, "admin_faction_rules_organization"),
    (Society, "admin_faction_rules_society"),
    (MissionOptionOpponentLine, "admin_placement_mission"),
    (WorshippedBeing, "admin_being_service"),
)


def builder_url(obj: object) -> str:
    """The custom-admin-page builder route for ``obj``, or "" when it has none.

    Generalised from ``upbringing_builder_tags.builder_url`` (#3660) so the
    Beginnings change form's "Open the tradition slate" object tool (#3675)
    shares the same lookup rather than re-deriving it. ``OriginTemplate``
    opens on the Upbringing Builder; ``Beginnings`` opens on the tradition
    slate page keyed by its own pk; ``Distinction`` opens on the Distinction
    Builder (#3675 Task 8); a Soulfray ``ConditionStage`` opens on the Soulfray
    Stage Builder (#4089). Any other condition's stage has no builder. A
    ``CreatureTemplate`` opens on the Standoff Profile Builder (#4354). An ``Organization``
    or ``Society`` opens on its Faction Rules page, and a mission option opponent line on
    its Placement page (#4361). A ``WorshippedBeing`` opens on the Being Service
    builder (#4333).
    """
    if isinstance(obj, ConditionStage):
        if obj.pk and is_soulfray_stage(obj):
            return reverse("admin_soulfray_builder", args=[obj.pk])
        return ""
    for model, url_name in _BUILDER_ROUTES:
        if isinstance(obj, model):
            return reverse(url_name, args=[obj.pk]) if obj.pk else ""
    return ""


def builder_label(obj: object) -> str:
    """The object-tool link text for ``builder_url(obj)``; "" when it has no builder page."""
    if isinstance(obj, OriginTemplate):
        return "Open in Upbringing Builder"
    if isinstance(obj, Beginnings):
        return "Open the tradition slate"
    if isinstance(obj, Distinction):
        return "Open in Distinction Builder"
    if isinstance(obj, ConditionStage) and is_soulfray_stage(obj):
        return "Open in Soulfray Stage Builder"
    if isinstance(obj, CreatureTemplate):
        return "Open the Standoff Profile Builder"
    if isinstance(obj, WorshippedBeing):
        return "Open the Being Service builder"
    if isinstance(obj, (Organization, Society)):
        return "Edit its faction rules"
    if isinstance(obj, MissionOptionOpponentLine):
        return "Open the Placement page"
    return ""


def workbench_editor_url(model_label: str, pk: object) -> str:
    """Build the Authoring Workbench editor deep-link for one row.

    Unlike a per-model admin change-form URL, this always resolves -
    ``admin_authoring_editor`` is a fixed route, not one built off the admin
    registry (#3019 review, Item 2).
    """
    query = urlencode({"model": model_label, "pk": pk})
    return f"{reverse('admin_authoring_editor')}?{query}"


def workbench_page_url(model_label: str, pk: object) -> str:
    """Build the Authoring Workbench PAGE link that opens one row (#4155).

    For a link a browser navigates to (a change form's object tool, a bookmark):
    the dashboard, which loads htmx and swaps the row's editor fragment into its
    own panel on load. ``workbench_editor_url`` above is the fragment's own URL
    and belongs only in an ``hx-get`` inside that page: served as a document it
    has no htmx, and every action button on it fell back to a plain form POST
    the fragment view never reads, which dropped the edit.
    """
    query = urlencode({"model": model_label, "pk": pk})
    return f"{reverse('admin_authoring')}?{query}"


def admin_change_url(model_label: str, pk: object) -> str | None:
    """Stock-admin change-form link for one row, or ``None`` when it has no ``ModelAdmin``.

    The inverse of ``workbench_editor_url``: the workbench editor only ever
    exposes a row's prose fields, so this is the link an author follows to
    reach everything else on the row (sort orders, flags, foreign keys).

    Not every credited model has a registered ``ModelAdmin`` (inline-only
    payload rows such as ``magic.TechniqueDamageProfile`` never get one) - so checking
    ``admin.site._registry`` first keeps
    an unregistered model from ever reaching ``reverse()``. The
    ``NoReverseMatch`` catch is defense in depth for any other reason
    ``admin:<app_label>_<model_name>_change`` might not resolve. Callers
    render nothing for ``None`` rather than a dead link.

    Promoted here from ``authoring.views._admin_change_url`` so the
    related-entries pane and the backlog queue build the same URL the same
    way - the ``(model_label, pk)`` signature both ``RelatedEntry`` and
    ``BacklogRow`` can satisfy, since neither carries the model class itself.
    """
    return _registered_admin_reverse(model_label, "change", args=(pk,))


def admin_changelist_url(model_label: str) -> str | None:
    """Stock-admin changelist link for a whole model, or ``None`` when it has no ``ModelAdmin``.

    The table-level sibling of ``admin_change_url``. The Required content panel
    (#3831) links every dependency to the page where staff author its rows, and a
    model with no registered admin renders no link rather than a dead one.
    """
    return _registered_admin_reverse(model_label, "changelist")


def _registered_admin_reverse(
    model_label: str, view: str, *, args: tuple[object, ...] = ()
) -> str | None:
    """Reverse ``admin:<app>_<model>_<view>`` only for a model registered in ``admin.site``.

    Checking the registry first keeps an unregistered model from ever reaching
    ``reverse()``; the ``NoReverseMatch`` catch is defense in depth.
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
        return reverse(f"admin:{app_label}_{model_name}_{view}", args=args)
    except NoReverseMatch:
        return None
