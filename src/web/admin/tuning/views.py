"""Game Tuning dashboard — superuser-only difficulty analytics + simulation (#1221).

The dashboard page (`tuning_dashboard`) renders a skeleton of four panels, each
an HTMX fragment loaded on page load. Tasks 2/3/4/6 replace the stub fragment
views below (`_checks_fragment`, `_consequences_fragment`,
`_conditions_fragment`, `_simulation_fragment`) with real analytics.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


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
def _checks_fragment(_request: HttpRequest) -> HttpResponse:
    """Stub for the checks-analytics panel; replaced in Task 2."""
    return HttpResponse("<p>Loading soon.</p>")


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
