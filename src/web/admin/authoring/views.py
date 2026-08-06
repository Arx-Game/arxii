"""Authoring Workbench dashboard: worst-first backlog queue across every credited
content model (#3019).

The dashboard page (`authoring_dashboard`) renders a skeleton of two
HTMX-loaded panels - domain stats and the queue itself - both scanning the
same `build_backlog()` result (Task 2, `web.admin.authoring.backlog`). The
queue panel caps its display at 100 rows and applies `?domain=`, `?status=`,
and `?q=` filters over the already-sorted rows in a single Python-side scan
(no per-filter rescans, no extra DB queries - `build_backlog()` is the only
query-issuing call in either fragment).

Task 4 gates the dashboard on a linked `ContentContributor` (see
`web.admin.authoring.contributors`): an unlinked account gets the setup panel
in place of the stats/queue skeleton, and `authoring_setup` is the plain-POST
handler that panel submits to.

Task 5 replaces `authoring_editor` wholesale with the real row editor; it is
registered here only so the queue panel's row links resolve to something
during this task's tests, per the URL name it will keep using
(`admin_authoring_editor`).
"""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from web.admin.authoring.backlog import BacklogRow, build_backlog
from web.admin.authoring.contributors import current_contributor, link_contributor
from web.admin.constants import BacklogStatusFilter
from web.admin.tuning.views import superuser_required
from world.contributors.models import ContentContributor

_QUEUE_DISPLAY_CAP = 100


def _setup_required(request: HttpRequest) -> bool:
    return current_contributor(request.user) is None


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
    """Authoring Workbench dashboard: setup panel first, stats + queue after.

    An unlinked account sees the setup panel in place of the stats/queue
    skeleton (#3019 Task 4) - every downstream panel assumes a contributor
    identity, so the gate wires one up before any of them ever load.
    """
    context = {"title": "Authoring Workbench", "setup_required": _setup_required(request)}
    if context["setup_required"]:
        context["unlinked_contributors"] = ContentContributor.objects.filter(
            player_data__isnull=True
        )
        context["suggested_name"] = request.user.username
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


@superuser_required
@require_POST
def authoring_setup(request: HttpRequest) -> HttpResponse:
    """Create-or-pick a contributor and link it to the account (#3019 Task 4).

    A plain form POST from `_setup_panel.html`, not an HTMX fragment - the
    happy path is a full-page redirect back to the dashboard, which now
    renders the normal stats/queue skeleton once the link exists.

    Two ways a repeat submit can land here, both handled without a 500: a
    sequential re-POST from an already-linked account (a stale tab, a slow
    double-click that landed after the first response) is caught by the
    `current_contributor` check right below and flashed as a no-op; a truly
    concurrent double-submit that gets past that check on both requests races
    unique-constraint writes inside `link_contributor`, which resolves it
    itself - idempotent success if the race linked this same account, a
    coherent "someone else just took it" `ValueError` otherwise. Either way
    this view only ever sees a `ValueError` or a contributor, never a raw
    `IntegrityError`.
    """
    if current_contributor(request.user) is not None:
        messages.info(request, "Your author credit is already linked.")
        return redirect("admin_authoring")

    name = request.POST.get("name", "")
    existing_pk_raw = request.POST.get("existing_pk", "")
    existing_pk = int(existing_pk_raw) if existing_pk_raw.isdigit() else None

    try:
        contributor = link_contributor(request.user, name=name, existing_pk=existing_pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("admin_authoring")

    messages.success(request, f'Linked your author credit to "{contributor.name}".')
    return redirect("admin_authoring")
