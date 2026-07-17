"""Superuser-only external content-repo load surface (#1220).

Mirrors the seed-button pattern (``seed_views.py``): the private content
repository (never named here) is located via the ``CONTENT_REPO_PATH``
environment variable, already loaded into the process env by the ``arx``
CLI's dotenv handling — this module reads it via ``os.environ``, it does
not re-parse ``.env``. Drives ``core_management.content_fixtures.
load_world_content`` (#2448) the same way ``tools/build_content_fixtures.py
--load`` does — content fixtures, then grid bundles, then a retry of any
fixture whose natural-key FK target (e.g. a ``StartingArea``'s
``default_starting_room``) only existed once the grid loaded.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import Error as DjangoDbError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST


def resolve_content_root() -> Path | None:
    """Return the configured content-repo path if set and a real directory."""
    raw = os.environ.get("CONTENT_REPO_PATH")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None
    return path


@staff_member_required
@require_GET
def content_load_confirm(request: HttpRequest) -> HttpResponse:
    """Render a confirm page describing what the content load will do."""
    if not request.user.is_superuser:
        raise PermissionDenied
    context = {"title": "Load private content repo"}
    return render(request, "admin/content_load_confirm.html", context)


@staff_member_required
@require_POST
def content_load_run(request: HttpRequest) -> HttpResponse:
    """Build + upsert the external content repo, then import grid bundles.

    Superuser-only; safe to re-run. ``build_all`` is called once directly,
    purely to read ``placeholder_counts`` for the flash message — cheap,
    side-effect-free parsing (not a second load); ``load_world_content`` does
    the actual content-fixtures -> grid-bundles -> deferred-retry sequence
    (#2448) and owns every create/update/skip/grid count reported below.
    """
    if not request.user.is_superuser:
        raise PermissionDenied
    from core_management.content_fixtures import (  # noqa: PLC0415
        ContentError,
        build_all,
        load_world_content,
    )

    raw = os.environ.get("CONTENT_REPO_PATH")
    if not raw:
        messages.error(
            request,
            "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
            "local checkout of the private content repository.",
        )
        return HttpResponseRedirect(reverse("admin_game_setup"))

    content_root = Path(raw).expanduser()
    if not content_root.is_dir():
        messages.error(request, f"CONTENT_REPO_PATH does not exist: {content_root}")
        return HttpResponseRedirect(reverse("admin_game_setup"))

    try:
        placeholder_counts = build_all(content_root).placeholder_counts
        world_result = load_world_content(content_root)
    except ContentError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin_game_setup"))
    except DjangoDbError as exc:
        # Unlike the tools/build_content_fixtures.py CLI wrapper, this view
        # never needs to catch ImproperlyConfigured — an admin request only
        # reaches here with Django already fully configured. An unmigrated
        # or unreachable DB (e.g. the npc_roles/ faction_affiliation lookup,
        # or load_world_content's update_or_create/grid import) is the one
        # environmental failure mode left; surface it the same clean way as
        # ContentError instead of a raw 500.
        messages.error(
            request,
            f"Database error while loading content: {exc} "
            "(hint: run `arx manage migrate` to bring the dev DB schema up to date).",
        )
        return HttpResponseRedirect(reverse("admin_game_setup"))

    placeholders = sum(placeholder_counts.values())
    skip_msg = f", {len(world_result.skipped)} skipped" if world_result.skipped else ""
    deferred_msg = (
        f", {world_result.deferred_resolved} deferred-resolved"
        if world_result.deferred_resolved
        else ""
    )
    grid = world_result.grid
    grid_created = grid.created_areas + grid.created_rooms + grid.created_exits
    grid_updated = grid.updated_areas + grid.updated_rooms + grid.updated_exits
    grid_msg = ""
    if grid_created or grid_updated:
        grid_msg = f"; grid: {grid_created} created, {grid_updated} updated"
    messages.success(
        request,
        f"Content load: {world_result.created} created, {world_result.updated} updated, "
        f"{placeholders} placeholder entries{skip_msg}{deferred_msg}{grid_msg}",
    )
    for skip in world_result.skipped:
        messages.warning(request, skip)
    for report in grid.reports:
        messages.warning(request, report)
    return HttpResponseRedirect(reverse("admin_game_setup"))
