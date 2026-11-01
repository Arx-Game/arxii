"""The Missing combat content page (#4906, slice 4 of #4843).

One row per open combat role flag (``combat_role_flags``): what is flagged and a link to
fix each flagged row. Read only, superuser-only like the Game Ops dashboard it sits under.
"""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from web.admin.tuning.combat_role_flags import collect_combat_role_flags
from web.admin.tuning.views import superuser_required


@superuser_required
@require_GET
def combat_content(request: HttpRequest) -> HttpResponse:
    """Every open missing combat content flag, each flagged row linked to its fix page."""
    open_flags = [row for row in collect_combat_role_flags() if not row.result.present]
    return render(
        request,
        "admin/tuning/combat_content.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": "Missing combat content",
            "open_flags": open_flags,
        },
    )
