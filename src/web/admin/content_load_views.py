"""Superuser-only external content-repo load surface (#1220).

Mirrors the seed-button pattern (``seed_views.py``): the private content
repository (never named here) is located via the ``CONTENT_REPO_PATH``
environment variable, already loaded into the process env by the ``arx``
CLI's dotenv handling — this module reads it via ``os.environ``, it does
not re-parse ``.env``. Drives ``core_management.content_fixtures.build_all``
+ ``load_entries`` the same way ``tools/build_content_fixtures.py --load``
does.
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
    """Build + upsert the external content repo. Superuser-only; safe to re-run."""
    if not request.user.is_superuser:
        raise PermissionDenied
    from core_management.content_fixtures import (  # noqa: PLC0415
        ContentError,
        build_all,
        load_entries,
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
        result = build_all(content_root)
        created, updated = load_entries(result)
    except ContentError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin_game_setup"))
    except DjangoDbError as exc:
        # Unlike the tools/build_content_fixtures.py CLI wrapper, this view
        # never needs to catch ImproperlyConfigured — an admin request only
        # reaches here with Django already fully configured. An unmigrated
        # or unreachable DB (e.g. the npc_roles/ faction_affiliation lookup,
        # or load_entries' update_or_create) is the one environmental
        # failure mode left; surface it the same clean way as ContentError
        # instead of a raw 500.
        messages.error(
            request,
            f"Database error while loading content: {exc} "
            "(hint: run `arx manage migrate` to bring the dev DB schema up to date).",
        )
        return HttpResponseRedirect(reverse("admin_game_setup"))
    placeholders = sum(result.placeholder_counts.values())
    skip_msg = f", {len(result.skipped)} skipped" if result.skipped else ""
    messages.success(
        request,
        f"Content load: {created} created, {updated} updated, "
        f"{placeholders} placeholder entries{skip_msg}",
    )
    for skip in result.skipped:
        messages.warning(request, skip)
    return HttpResponseRedirect(reverse("admin_game_setup"))
