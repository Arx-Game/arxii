"""Game Tuning dashboard — superuser-only difficulty analytics + simulation (#1221).

The dashboard page (`tuning_dashboard`) renders a skeleton of four panels, each
an HTMX fragment loaded on page load. Task 2 replaced the checks-panel stub
with `tuning_checks_fragment` (real analytics, see `checks_analytics.py`). Task 3
replaced the consequences-panel stub with `tuning_consequences_fragment` (see
`consequence_analytics.py`). Task 4 replaced the conditions-panel stub with
`tuning_conditions_fragment` (see `condition_analytics.py`). Task 6 still needs
to replace the remaining stub fragment view below (`_simulation_fragment`).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from actions.models.consequence_pools import ConsequencePool
from web.admin.tuning.checks_analytics import compute_chart_distributions, compute_matchup
from web.admin.tuning.condition_analytics import compute_condition_danger
from web.admin.tuning.consequence_analytics import inspect_pool, list_pools

_DEFAULT_ROLLER_POINTS = 25
_DEFAULT_TARGET_DIFFICULTY = 25
_DEFAULT_CONDITION_SEVERITY = 5


def _int_query_param(request: HttpRequest, name: str, default: int) -> int:
    """Parse a query-string int param, falling back to `default` if absent/invalid."""
    raw = request.GET.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def superuser_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Admin views in the tuning surface are superuser-only (mirrors game_setup)."""

    @wraps(view)
    def wrapped(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return staff_member_required(wrapped)


@superuser_required
def tuning_dashboard(request: HttpRequest) -> HttpResponse:
    """Game Tuning dashboard skeleton: four HTMX-loaded panels."""
    context = {"title": "Game Tuning"}
    return render(request, "admin/tuning/dashboard.html", context)


@superuser_required
def tuning_checks_fragment(request: HttpRequest) -> HttpResponse:
    """Checks-analytics panel: per-chart probability tables + a matchup sub-form (#1221).

    Sliders (`roll_modifier`, `roller_points`, `target_difficulty`) re-render this
    same fragment via `hx-get` query params so the panel form must live inside the
    fragment template (see `_checks_panel.html`).
    """
    roll_modifier = _int_query_param(request, "roll_modifier", 0)
    roller_points = _int_query_param(request, "roller_points", _DEFAULT_ROLLER_POINTS)
    target_difficulty = _int_query_param(request, "target_difficulty", _DEFAULT_TARGET_DIFFICULTY)

    context = {
        "distributions": compute_chart_distributions(roll_modifier=roll_modifier),
        "matchup": compute_matchup(
            roller_points=roller_points,
            target_difficulty=target_difficulty,
            roll_modifier=roll_modifier,
        ),
        "roll_modifier": roll_modifier,
        "roller_points": roller_points,
        "target_difficulty": target_difficulty,
    }
    return render(request, "admin/tuning/_checks_panel.html", context)


@superuser_required
def tuning_consequences_fragment(request: HttpRequest) -> HttpResponse:
    """Consequence-pool inspector panel: annotated entries for a selected pool (#1221).

    `pool` query param selects which pool to inspect via its `<select>`
    re-render (`hx-get` on change); defaults to the first pool by name. The
    selector form lives inside the fragment template so re-renders preserve it.
    """
    pools = list_pools()
    default_pool_id = pools[0][0] if pools else 0
    selected_pool_id = _int_query_param(request, "pool", default_pool_id)

    pool = ConsequencePool.objects.filter(pk=selected_pool_id).first()
    inspection = inspect_pool(pool) if pool is not None else None

    context = {
        "pools": pools,
        "selected_pool_id": selected_pool_id,
        "inspection": inspection,
    }
    return render(request, "admin/tuning/_consequences_panel.html", context)


@superuser_required
def tuning_conditions_fragment(request: HttpRequest) -> HttpResponse:
    """Condition-danger panel: ranks conditions by severity/DoT danger score (#1221).

    `severity` query param drives the slider re-render (`hx-get` on input) so
    the form lives inside the fragment template (see `_conditions_panel.html`).
    """
    severity = _int_query_param(request, "severity", _DEFAULT_CONDITION_SEVERITY)

    context = {
        "rows": compute_condition_danger(at_severity=severity),
        "severity": severity,
    }
    return render(request, "admin/tuning/_conditions_panel.html", context)


@superuser_required
def _simulation_fragment(_request: HttpRequest) -> HttpResponse:
    """Stub for the simulation panel; replaced in Task 6."""
    return HttpResponse("<p>Loading soon.</p>")
