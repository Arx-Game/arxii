"""Game Tuning dashboard — superuser-only difficulty analytics + simulation (#1221).

The dashboard page (`tuning_dashboard`) renders a skeleton of four panels, each
an HTMX fragment loaded on page load. Task 2 replaced the checks-panel stub
with `tuning_checks_fragment` (real analytics, see `checks_analytics.py`).
Tasks 3/4/6 still need to replace the remaining stub fragment views below
(`_consequences_fragment`, `_conditions_fragment`, `_simulation_fragment`).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from web.admin.tuning.checks_analytics import compute_chart_distributions, compute_matchup

_DEFAULT_ROLLER_POINTS = 25
_DEFAULT_TARGET_DIFFICULTY = 25


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
def _consequences_fragment(_request: HttpRequest) -> HttpResponse:
    """Stub for the consequences panel; replaced in Task 3."""
    return HttpResponse("<p>Loading soon.</p>")


@superuser_required
def _conditions_fragment(_request: HttpRequest) -> HttpResponse:
    """Stub for the conditions panel; replaced in Task 4."""
    return HttpResponse("<p>Loading soon.</p>")


@superuser_required
def _simulation_fragment(_request: HttpRequest) -> HttpResponse:
    """Stub for the simulation panel; replaced in Task 6."""
    return HttpResponse("<p>Loading soon.</p>")
