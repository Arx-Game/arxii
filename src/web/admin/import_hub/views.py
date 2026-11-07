"""The Import Data hub (#5001).

The header's Import Data button opens this page instead of the fixture upload: one card
per route content comes in by, each saying what it does to rows that already exist. The
table pastes and the content-repo load are superuser-only and render only for a
superuser; the fixture upload keeps today's staff gate and its own URL.
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core_management.content_repo import resolve_content_root

_TITLE = "Import Data"


@staff_member_required
@require_GET
def import_hub(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "admin/import_hub.html",
        {"title": _TITLE, "content_repo_configured": resolve_content_root() is not None},
    )
