"""Superuser-only 'Load sane defaults' admin action (#651)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import Error as DjangoDbError
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
    """Run the seed orchestrator. Superuser-only; idempotent.

    ``seed_dev_database()`` (#2474 Task 3) now loads the arx2-lore content
    repo first and raises ``ContentError`` loudly when ``CONTENT_REPO_PATH``
    is unset or invalid — no silent skip, no synthetic fallback. Mirrors
    ``content_load_views.content_load_run``'s catch-and-flash pattern so a
    missing/misconfigured content repo surfaces as a friendly message on the
    Game Setup hub instead of a raw 500.
    """
    if not request.user.is_superuser:
        raise PermissionDenied
    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from world.seeds.database import seed_dev_database  # noqa: PLC0415

    try:
        report = seed_dev_database()
    except ContentError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin_game_setup"))
    except DjangoDbError as exc:
        # Mirrors content_load_run: an unmigrated/unreachable DB reached
        # while loading content is the one environmental failure mode left
        # once CONTENT_REPO_PATH itself resolves; surface it the same clean
        # way as ContentError instead of a raw 500.
        messages.error(
            request,
            f"Database error while seeding: {exc} "
            "(hint: run `arx manage migrate` to bring the dev DB schema up to date).",
        )
        return HttpResponseRedirect(reverse("admin_game_setup"))

    messages.success(
        request,
        f"Seeded {report.created_total} new rows across "
        f"{len(report.clusters)} clusters (existing rows untouched).",
    )
    return HttpResponseRedirect(reverse("admin_game_setup"))
