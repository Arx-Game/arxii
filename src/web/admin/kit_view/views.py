"""The kit view page (#4918, slice 5 of #4843): one real character's combat kit, read only.

Staff who can view or change ``CharacterSheet`` may open it; nothing on the page writes.
The reads live in ``live``.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from web.admin.combat_roles import can_view
from web.admin.kit_view import live
from world.character_sheets.models import CharacterSheet


def _require_view(request: HttpRequest) -> None:
    if not can_view(request.user, CharacterSheet):
        raise PermissionDenied


@staff_member_required
@require_GET
def kit_view(request: HttpRequest, sheet_pk: int) -> HttpResponse:
    """One character's techniques with what the vow adds, its chosen picks and sheet."""
    _require_view(request)
    sheet = get_object_or_404(CharacterSheet.objects.select_related("character"), pk=sheet_pk)
    kit = live.kit_for(sheet)
    return render(
        request,
        "admin/kit_view/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": kit.name,
            "kit": kit,
        },
    )


@staff_member_required
@require_GET
def kit_view_pick(request: HttpRequest) -> HttpResponse:
    """GET ``?pk=`` redirect target for the Combat roles panel's character picker."""
    _require_view(request)
    raw = request.GET.get("pk", "")
    if not raw.isdigit() or not CharacterSheet.objects.filter(pk=raw).exists():
        return HttpResponseBadRequest("Pick a character to open.")
    return redirect("admin_kit_view", sheet_pk=int(raw))
