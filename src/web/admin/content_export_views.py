"""Superuser-only export-to-content-repo surface.

Mirrors the content-load pattern: the private content repository (never named
here) is located via the ``CONTENT_REPO_PATH`` environment variable. Drives
``core_management.content_export.export_to_content_repo`` the same way
``tools/export_content.py`` does.
"""

from __future__ import annotations

import os
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

    content_root = os.environ.get("CONTENT_REPO_PATH")
    context = {
        "title": "Export to content repo",
        "models": models_info,
        "total_records": total_records,
        "total_models": len(models_info),
        "content_repo_configured": bool(content_root and Path(content_root).is_dir()),
    }
    return render(request, "admin/content_export_preview.html", context)


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
    return HttpResponseRedirect(reverse("admin_game_setup"))
