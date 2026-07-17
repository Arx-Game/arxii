"""Admin 'Game Setup' hub view — wayfinding + content inventory (#1333).

Superuser-only landing page for configuring a freshly-cloned Arx instance.
Mirrors the seed-button gate (ADR-0022): superuser-only, read-only.
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET


@staff_member_required
@require_GET
def game_setup(request: HttpRequest) -> HttpResponse:
    """Read-only hub: the clone -> seed -> tweak -> export flow + per-cluster inventory.

    The flow:
      1. Load sane defaults (the Big Button) — populates a baseline playable game.
      2. Author content — species, paths, magic, combat, traits, etc. via the
         World apps on the admin index.
      3. Load private content repo — builds + upserts the maintainers' external
         content repo when `CONTENT_REPO_PATH` is configured (#1220).
      4. Tune mechanics — the Game Tuning dashboard (#1221): difficulty
         analytics + simulation.
      5. Monitor the live game — the Game Ops dashboard (#1221): progression,
         economy, story/GM, reports-queue, and technical-health analytics.
      6. Export / Import — save the configuration as a portable JSON fixture.

    The inventory shows, per seeded cluster, the representative content rows and
    their current counts — empty rows are content gaps to fill.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from world.seeds.clusters import seeded_models_by_cluster  # noqa: PLC0415

    inventory = [
        {
            "cluster": cluster,
            "models": [
                {
                    "name": m._meta.verbose_name_plural.title(),  # noqa: SLF001
                    "count": m.objects.count(),
                }
                for m in models
            ],
        }
        for cluster, models in seeded_models_by_cluster().items()
    ]
    context = {
        "title": "Game Setup",
        "inventory": inventory,
        "seed_url": reverse("admin_seed"),
        "export_url": reverse("admin_export_preview"),
        "import_url": reverse("admin_import_upload"),
        "content_repo_configured": resolve_content_root() is not None,
        "content_load_url": reverse("admin_content_load"),
        "world_apps": [
            "character_creation",
            "character_sheets",
            "classes",
            "forms",
            "species",
            "traits",
            "magic",
            "realms",
        ],
    }
    return render(request, "admin/game_setup.html", context)
