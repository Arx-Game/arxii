"""Authoring Workbench dashboard: worst-first backlog queue across every credited
content model (#3019).

The dashboard page (`authoring_dashboard`) renders a skeleton of two
HTMX-loaded panels - domain stats and the queue itself - both scanning the
same `build_backlog()` result (Task 2, `web.admin.authoring.backlog`). The
queue panel caps its display at 100 rows and applies `?domain=`, `?status=`,
and `?q=` filters over the already-sorted rows in a single Python-side scan
(no per-filter rescans, no extra DB queries - `build_backlog()` is the only
query-issuing call in either fragment).

Task 5 replaces `authoring_editor` wholesale with the real row editor; it is
registered here only so the queue panel's row links resolve to something
during this task's tests, per the URL name it will keep using
(`admin_authoring_editor`).
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from web.admin.authoring.backlog import BacklogRow, build_backlog
from web.admin.constants import BacklogStatusFilter
from web.admin.tuning.views import superuser_required

_QUEUE_DISPLAY_CAP = 100


def _setup_required(request: HttpRequest) -> bool:  # noqa: ARG001 - Task 4 reads request.user
    # Task 4 replaces this with the contributor check.
    return False


def _row_matches(row: BacklogRow, domain: str, status: str, query: str) -> bool:
    """One row's pass/fail against every active filter, checked in one call.

    Called from a single list comprehension over the full row list in
    `_filtered_rows`, so the combined filter set is one scan regardless of
    how many of `domain`/`status`/`query` are actually set.
    """
    if domain and row.domain != domain:
        return False
    if status == BacklogStatusFilter.PLACEHOLDER and not row.has_placeholder:
        return False
    if status == BacklogStatusFilter.UNWRITTEN and row.written:
        return False
    if status == BacklogStatusFilter.UNREVIEWED and row.reviewed:
        return False
    if query and query not in row.identity.lower():
        return False
    return True


def _filtered_rows(rows: list[BacklogRow], request: HttpRequest) -> list[BacklogRow]:
    domain = request.GET.get("domain") or ""
    status = request.GET.get("status") or ""
    query = (request.GET.get("q") or "").strip().lower()
    return [row for row in rows if _row_matches(row, domain, status, query)]


@superuser_required
def authoring_dashboard(request: HttpRequest) -> HttpResponse:
    """Authoring Workbench dashboard skeleton: stats + queue HTMX panels."""
    if _setup_required(request):
        raise PermissionDenied
    context = {"title": "Authoring Workbench"}
    return render(request, "admin/authoring/dashboard.html", context)


@superuser_required
def authoring_stats_fragment(request: HttpRequest) -> HttpResponse:
    """Per-domain rollup panel: rows/unwritten/unreviewed/word counts."""
    _, stats = build_backlog()
    context = {"stats": stats}
    return render(request, "admin/authoring/_stats_panel.html", context)


@superuser_required
def authoring_queue_fragment(request: HttpRequest) -> HttpResponse:
    """Worst-first queue panel: filtered, capped at `_QUEUE_DISPLAY_CAP` rows.

    `domain`/`status`/`q` query params re-render this same fragment via
    `hx-get` (see `_queue_panel.html`), so the filter form lives inside the
    fragment template the same way the tuning panels' forms do.
    """
    rows, _ = build_backlog()
    domains = sorted({row.domain for row in rows})

    filtered = _filtered_rows(rows, request)
    total = len(filtered)
    visible = filtered[:_QUEUE_DISPLAY_CAP]

    context = {
        "rows": visible,
        "total": total,
        "display_cap": _QUEUE_DISPLAY_CAP,
        "capped": total > _QUEUE_DISPLAY_CAP,
        "domains": domains,
        "selected_domain": request.GET.get("domain", ""),
        "selected_status": request.GET.get("status", ""),
        "query": request.GET.get("q", ""),
    }
    return render(request, "admin/authoring/_queue_panel.html", context)


@superuser_required
def authoring_editor(request: HttpRequest) -> HttpResponse:
    """Editor fragment stub (#3019 Task 3).

    Task 5 replaces this view wholesale with the real row editor form. For
    now it renders a loading shell keyed off the `model`/`pk` query params
    the queue panel's row links carry, so those links resolve to a visible
    response during this task and every task after it until Task 5 lands.
    """
    context = {
        "model_label": request.GET.get("model", ""),
        "pk": request.GET.get("pk", ""),
    }
    return render(request, "admin/authoring/_editor_panel.html", context)
