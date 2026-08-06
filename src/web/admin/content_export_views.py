"""Superuser-only export-to-content-repo surface.

Mirrors the content-load pattern: the private content repository (never named
here) is located via the ``CONTENT_REPO_PATH`` environment variable. Drives
``core_management.content_export.export_to_content_repo`` the same way
``tools/export_content.py`` does.
"""

from __future__ import annotations

from pathlib import Path

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

    from core.app_domains import resolve_model_by_name  # noqa: PLC0415
    from core_management.content_export import CONTENT_MODELS  # noqa: PLC0415

    models_info = []
    total_records = 0
    for model_label in sorted(CONTENT_MODELS):
        # model_label is "<domain>.<model_name>", not a real Django app_label
        # post-collapse (#2906) — resolve by model name, not apps.get_model().
        app_label, model_name = model_label.split(".")
        try:
            model = resolve_model_by_name(model_label)
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


def _refuse_if_on_session_branch(
    request: HttpRequest, content_root: Path | None
) -> HttpResponse | None:
    """Refuse a corpus export while the checkout is on the row-export session branch.

    A corpus-wide export writes to the checkout's actual working tree, same
    as a row export does - running it while the checkout is still on the
    row-export session branch would mix a whole-corpus pass into that
    branch's small, per-row commits (#3018 review). The row-export flow
    never touches main, so this can only ever misfire the other direction.
    Split out of ``content_export_run`` (ruff C901) to keep that view's own
    branching under the complexity ceiling.

    A ``ContentPushError`` here means the checkout isn't a usable git repo at
    all (or the branch lookup otherwise failed) - that can never be the
    session branch, so this guard stays silent and lets the export attempt
    proceed to its own, more specific error handling.
    """
    from core_management.content_push import ContentPushError  # noqa: PLC0415
    from core_management.content_session import SESSION_BRANCH, _current_branch  # noqa: PLC0415

    if content_root is None:
        return None
    try:
        on_session_branch = _current_branch(content_root) == SESSION_BRANCH
    except ContentPushError:
        return None
    if not on_session_branch:
        return None
    messages.error(
        request,
        "The content checkout is on the row-export session branch. Finish "
        "or discard the session before running a corpus export.",
    )
    return HttpResponseRedirect(reverse("admin_game_setup"))


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
    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from core_management.grid_export import export_grid_bundles  # noqa: PLC0415

    content_root = resolve_content_root()
    bail = _refuse_if_on_session_branch(request, content_root)
    if bail is not None:
        return bail

    # Off by default: the export withholds rows the corpus does not already have,
    # so a database seeded with sample content cannot launder them in as lore
    # (#2890). Ticking the box is the authoring path for genuinely new rows.
    allow_additions = bool(request.POST.get("allow_additions"))

    try:
        result = export_to_content_repo(allow_additions=allow_additions)
    except ContentExportError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin_game_setup"))

    messages.success(
        request,
        f"Content export: {result.total_records} records -> "
        f"{len(result.written)} file(s), {len(result.skipped)} skipped, "
        f"{len(result.errors)} error(s).",
    )
    if result.added:
        messages.success(
            request,
            f"Added {result.added_count} new row(s): "
            + ", ".join(f"{label} ({len(keys)})" for label, keys in sorted(result.added.items())),
        )
    if result.withheld:
        messages.warning(
            request,
            f"Withheld {result.withheld_count} row(s) the content repo does not have — "
            "re-run with 'allow additions' to push them, or leave them if they are "
            "sample/seed rows: "
            + ", ".join(
                f"{label} ({len(keys)})" for label, keys in sorted(result.withheld.items())
            ),
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
