"""The combo map pages (#4891, slice 3 of #4843): one per property, one per condition.

Read only. Staff who can view the property or condition model may open them; nothing on
the page writes. The reads live in ``live``; the setter and reader lists in ``sources``.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Model
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from web.admin.combat_roles import can_view
from web.admin.combo_map import live
from world.conditions.models import ConditionTemplate
from world.mechanics.models import Property


def _require_view(request: HttpRequest, model: type[Model]) -> None:
    if not can_view(request.user, model):
        raise PermissionDenied


def _render(request: HttpRequest, combo: live.ComboMap | None) -> HttpResponse:
    if combo is None:
        raise Http404
    return render(
        request,
        "admin/combo_map/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": combo.name,
            "combo": combo,
            "is_property": combo.kind == live.PROPERTY_KIND,
        },
    )


@staff_member_required
@require_GET
def combo_map_property(request: HttpRequest, pk: int) -> HttpResponse:
    """What sets and what reads one property."""
    _require_view(request, Property)
    return _render(request, live.property_map(pk))


@staff_member_required
@require_GET
def combo_map_condition(request: HttpRequest, pk: int) -> HttpResponse:
    """What sets one condition, and what reads it and each property it carries."""
    _require_view(request, ConditionTemplate)
    return _render(request, live.condition_map(pk))


def _picked_pk(request: HttpRequest, model: type[Model]) -> int | None:
    raw = request.GET.get("pk", "")
    if not raw.isdigit() or not model.objects.filter(pk=raw).exists():
        return None
    return int(raw)


@staff_member_required
@require_GET
def combo_map_property_pick(request: HttpRequest) -> HttpResponse:
    """GET ``?pk=`` redirect target for the Combat roles panel's property picker."""
    _require_view(request, Property)
    pk = _picked_pk(request, Property)
    if pk is None:
        return HttpResponseBadRequest("Pick a property to open.")
    return redirect("admin_combo_map_property", pk=pk)


@staff_member_required
@require_GET
def combo_map_condition_pick(request: HttpRequest) -> HttpResponse:
    """GET ``?pk=`` redirect target for the Combat roles panel's condition picker."""
    _require_view(request, ConditionTemplate)
    pk = _picked_pk(request, ConditionTemplate)
    if pk is None:
        return HttpResponseBadRequest("Pick a condition to open.")
    return redirect("admin_combo_map_condition", pk=pk)
