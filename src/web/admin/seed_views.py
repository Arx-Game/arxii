"""Superuser-only 'Load sane defaults' admin action (#651)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST


@staff_member_required
@require_GET
def seed_confirm(request: HttpRequest) -> HttpResponse:
    """Render a confirm page describing what seeding will do."""
    return render(request, "admin/seed_confirm.html", {"title": "Load sane defaults"})


@staff_member_required
@require_POST
def seed_run(request: HttpRequest) -> HttpResponse:
    """Run the seed orchestrator. Superuser-only; idempotent."""
    if not request.user.is_superuser:
        raise PermissionDenied
    from world.seeds.database import seed_dev_database  # noqa: PLC0415

    report = seed_dev_database()
    messages.success(
        request,
        f"Seeded {report.created_total} new rows across "
        f"{len(report.clusters)} clusters (existing rows untouched).",
    )
    return HttpResponseRedirect(reverse("admin_game_setup"))
