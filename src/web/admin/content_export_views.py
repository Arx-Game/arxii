"""Superuser-only export-to-content-repo surface.

Mirrors the content-load pattern: the private content repository (never named
here) is located via the ``CONTENT_REPO_PATH`` environment variable. Drives
``core_management.content_export.export_to_content_repo`` the same way
``tools/export_content.py`` does.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, OperationalError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST


@staff_member_required
@require_GET
def content_export_preview(request: HttpRequest) -> HttpResponse:
    """Show a preview of what would be exported."""
    if not request.user.is_superuser:
        raise PermissionDenied

    from django.apps import apps  # noqa: PLC0415

    from core_management.content_export import CONTENT_MODELS  # noqa: PLC0415

    models_info = []
    total_records = 0
    for model_label in sorted(CONTENT_MODELS):
        app_label, model_name = model_label.split(".")
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        try:
            count = model.objects.count()
        except (DatabaseError, OperationalError):
            continue
        if count > 0:
            models_info.append(
                {
                    "label": model_label,
                    "app_label": app_label,
                    "model_name": model_name,
                    "count": count,
                    "output": f"fixtures/{app_label}/{model_name}.json",
                }
            )
            total_records += count

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415

    context = {
        "title": "Export to content repo",
        "models": models_info,
        "total_records": total_records,
        "total_models": len(models_info),
        "content_repo_configured": resolve_content_root() is not None,
    }
    context.update(_grid_preview_context())
    return render(request, "admin/content_export_preview.html", context)


def _grid_preview_context() -> dict:
    """Authored-area/room counts for the grid export preview block.

    Read-only mirror of ``core_management.grid_export.export_grid_bundles``'s
    selection query — never calls it directly, since that writes files.
    """
    from django.db.models import Count  # noqa: PLC0415

    from core_management.grid_export import find_unhoused_authored_rooms  # noqa: PLC0415
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    try:
        areas = list(Area.objects.filter(origin=GridOrigin.AUTHORED).order_by("slug"))
        unhoused_rooms = find_unhoused_authored_rooms()
    except (DatabaseError, OperationalError):
        return {
            "grid_areas": [],
            "grid_area_count": 0,
            "grid_room_count": 0,
            "grid_unhoused_rooms": [],
        }

    room_counts_by_area = {
        row["area_id"]: row["n"]
        for row in RoomProfile.objects.filter(area__in=areas, origin=GridOrigin.AUTHORED)
        .values("area_id")
        .annotate(n=Count("pk"))
    }

    grid_areas = []
    grid_room_count = 0
    for area in areas:
        room_count = room_counts_by_area.get(area.pk, 0)
        grid_room_count += room_count
        grid_areas.append(
            {
                "slug": area.slug,
                "name": area.name,
                "room_count": room_count,
                "output": f"fixtures/grid/{area.slug}.json" if area.slug else None,
            }
        )
    return {
        "grid_areas": grid_areas,
        "grid_area_count": len(grid_areas),
        "grid_room_count": grid_room_count,
        "grid_unhoused_rooms": unhoused_rooms,
    }


@staff_member_required
@require_POST
def content_export_run(request: HttpRequest) -> HttpResponse:
    """Export content models to the lore repo. Superuser-only."""
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_export import (  # noqa: PLC0415
        ContentExportError,
        export_to_content_repo,
    )
    from core_management.grid_export import export_grid_bundles  # noqa: PLC0415

    try:
        result = export_to_content_repo()
    except ContentExportError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin_game_setup"))

    messages.success(
        request,
        f"Content export: {result.total_records} records -> "
        f"{len(result.written)} file(s), {len(result.skipped)} skipped, "
        f"{len(result.errors)} error(s).",
    )
    for err in result.errors:
        messages.error(request, err)

    try:
        grid_result = export_grid_bundles()
    except ContentExportError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin_game_setup"))

    messages.success(
        request,
        f"Grid export: {grid_result.area_count} area(s), {grid_result.room_count} room(s) -> "
        f"{len(grid_result.written)} file(s), {len(grid_result.errors)} error(s).",
    )
    for line in grid_result.reports:
        messages.warning(request, line)
    for err in grid_result.errors:
        messages.error(request, err)
    return HttpResponseRedirect(reverse("admin_game_setup"))
