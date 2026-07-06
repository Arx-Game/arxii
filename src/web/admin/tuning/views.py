"""Game Tuning dashboard — superuser-only difficulty analytics + simulation (#1221).

The dashboard page (`tuning_dashboard`) renders a skeleton of four panels, each
an HTMX fragment loaded on page load. Task 2 replaced the checks-panel stub
with `tuning_checks_fragment` (real analytics, see `checks_analytics.py`). Task 3
replaced the consequences-panel stub with `tuning_consequences_fragment` (see
`consequence_analytics.py`). Task 4 replaced the conditions-panel stub with
`tuning_conditions_fragment` (see `condition_analytics.py`). Task 6 replaced the
simulation-panel stub with `tuning_simulation_fragment` (Monte Carlo party-vs-boss
batches over the real engine, see `world.combat.simulation`).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from actions.models.consequence_pools import ConsequencePool
from web.admin.tuning.checks_analytics import compute_chart_distributions, compute_matchup
from web.admin.tuning.condition_analytics import compute_condition_danger
from web.admin.tuning.consequence_analytics import inspect_pool, list_pools
from world.combat import simulation
from world.combat.constants import OpponentTier, RiskLevel
from world.combat.simulation import SimulationParams, SimulationReport

_DEFAULT_ROLLER_POINTS = 25
_DEFAULT_TARGET_DIFFICULTY = 25
_DEFAULT_CONDITION_SEVERITY = 5

# 24h — a simulation batch is expensive (dozens of full combat rounds), so a
# cached report should outlive a single admin session by a wide margin.
_SIMULATION_CACHE_TIMEOUT = 60 * 60 * 24
# Fixed pointer key: GET renders "the most recently cached result" by looking
# up whichever exact-param key was last written here, rather than trying to
# guess which of many possible param tuples the admin last ran.
_SIMULATION_LAST_KEY = "tuning-sim:last"


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


def _clamp(value: int, minimum: int, maximum: int) -> int:
    """Coerce `value` into `[minimum, maximum]` rather than rejecting it."""
    return max(minimum, min(maximum, value))


class SimulationRunForm(forms.Form):
    """Validates enum membership; clamps numeric ranges (#1221 Task 6).

    `tier`/`risk_level` are `ChoiceField`s — an unrecognized value is a real
    form error (there's no sane way to "clamp" a string into an enum member).
    The numeric fields are silently clamped into range instead of erroring, per
    the brief ("clamps iterations to 1..500 via the form") — a GM fat-fingering
    9999 iterations should get the capped run, not a rejected form.
    """

    party_size = forms.IntegerField()
    avg_level = forms.IntegerField()
    tier = forms.ChoiceField(choices=OpponentTier.choices)
    risk_level = forms.ChoiceField(choices=RiskLevel.choices)
    iterations = forms.IntegerField()

    def clean_party_size(self) -> int:
        return _clamp(self.cleaned_data["party_size"], 1, 8)

    def clean_avg_level(self) -> int:
        return _clamp(self.cleaned_data["avg_level"], 1, 30)

    def clean_iterations(self) -> int:
        return _clamp(self.cleaned_data["iterations"], 1, 500)


def _simulation_form_defaults() -> dict[str, Any]:
    """Initial values for a fresh GET form, mirroring `SimulationParams` defaults."""
    defaults = SimulationParams()
    return {
        "party_size": defaults.party_size,
        "avg_level": defaults.avg_level,
        "tier": defaults.tier,
        "risk_level": defaults.risk_level,
        "iterations": defaults.iterations,
    }


def _simulation_cache_key(params: SimulationParams) -> str:
    """Exact-param cache key, per the brief's tuple format."""
    return (
        f"tuning-sim:{params.party_size}:{params.avg_level}:{params.tier}:"
        f"{params.risk_level}:{params.iterations}:{params.round_cap}"
    )


def _round_count_histogram(round_counts: list[int]) -> list[dict[str, int]]:
    """Bucket `round_counts` into labeled bars: how many iterations ended in N rounds."""
    if not round_counts:
        return []
    counts: dict[int, int] = {}
    for rounds_used in round_counts:
        counts[rounds_used] = counts.get(rounds_used, 0) + 1
    max_count = max(counts.values())
    return [
        {"rounds": rounds_used, "count": count, "pct": round(count / max_count * 100)}
        for rounds_used, count in sorted(counts.items())
    ]


@superuser_required
def tuning_simulation_fragment(request: HttpRequest) -> HttpResponse:
    """Monte Carlo simulation panel: run + cache party-vs-boss batches (#1221 Task 6).

    GET renders the form (seeded with `SimulationParams` defaults) plus the most
    recently cached result, if any — tracked via the fixed `_SIMULATION_LAST_KEY`
    pointer so a plain page reload doesn't lose the last run. POST validates and
    clamps inputs through `SimulationRunForm`, runs the batch synchronously, and
    caches the report under both the exact-param key and the last-key pointer
    (24h timeout).

    Calls `simulation.run_party_vs_boss_simulation` via the module object (never
    `from world.combat.simulation import run_party_vs_boss_simulation` directly)
    so tests can patch the real function at its origin
    (`world.combat.simulation.run_party_vs_boss_simulation`) and still intercept
    this call — a bare `from ... import f` would bind a name here that patching
    the origin module wouldn't reach.
    """
    report: SimulationReport | None = None

    if request.method == "POST":
        form = SimulationRunForm(request.POST)
        if form.is_valid():
            params = SimulationParams(
                party_size=form.cleaned_data["party_size"],
                avg_level=form.cleaned_data["avg_level"],
                tier=form.cleaned_data["tier"],
                risk_level=form.cleaned_data["risk_level"],
                iterations=form.cleaned_data["iterations"],
            )
            report = simulation.run_party_vs_boss_simulation(params)
            cache_key = _simulation_cache_key(params)
            cache.set(cache_key, report, _SIMULATION_CACHE_TIMEOUT)
            cache.set(_SIMULATION_LAST_KEY, cache_key, _SIMULATION_CACHE_TIMEOUT)
    else:
        form = SimulationRunForm(initial=_simulation_form_defaults())
        last_key = cache.get(_SIMULATION_LAST_KEY)
        if last_key:
            report = cache.get(last_key)

    context = {
        "form": form,
        "report": report,
        "histogram": _round_count_histogram(report.round_counts) if report else [],
    }
    return render(request, "admin/tuning/_simulation_panel.html", context)
