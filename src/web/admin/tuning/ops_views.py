"""Game Ops dashboard — superuser-only live-game analytics (#1221 Task 7).

Parallel to the Game Tuning dashboard (`views.py`): a page skeleton of four
HTMX-loaded panels backed by the pure-read helpers in `metrics.py`.
Progression (XP/dev-points/level-ups + level distribution), Economy
(mint/sink/transfer + money supply), Story/GM (beats/scenes + activity
snapshot), and Reports (player-submissions queues linking to the React staff
pages).
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from web.admin.tuning.metrics import (
    WeeklySeries,
    economy_series,
    level_distribution,
    money_supply,
    progression_series,
    reports_snapshot,
    story_series,
    story_snapshot,
)
from web.admin.tuning.tech_health import collect_tech_health
from web.admin.tuning.views import superuser_required
from world.currency.constants import format_coppers


def _series_row(series: WeeklySeries) -> dict[str, Any]:
    """A `WeeklySeries` with each point's bar-fill percentage precomputed.

    Percentages (never raw magnitudes) drive `.bar` width in the template —
    the max across the series' own points is the 100% reference, floored at
    1 so an all-zero series doesn't divide by zero.
    """
    max_value = max((point.value for point in series.points), default=0.0) or 1.0
    return {
        "label": series.label,
        "points": [
            {
                "week_start": point.week_start,
                "value": point.value,
                "pct": round(point.value / max_value * 100),
            }
            for point in series.points
        ],
    }


@superuser_required
def ops_dashboard(request: HttpRequest) -> HttpResponse:
    """Game Ops dashboard skeleton: four HTMX-loaded panels."""
    context = {"title": "Game Ops"}
    return render(request, "admin/tuning/ops.html", context)


@superuser_required
def ops_progression_fragment(request: HttpRequest) -> HttpResponse:
    """Progression panel: weekly XP/dev-points/level-ups + level distribution."""
    levels = level_distribution()
    max_count = max((count for _level, count in levels), default=0) or 1
    context = {
        "series": [_series_row(s) for s in progression_series()],
        "level_distribution": [
            {"level": level, "count": count, "pct": round(count / max_count * 100)}
            for level, count in levels
        ],
    }
    return render(request, "admin/tuning/_progression_panel.html", context)


@superuser_required
def ops_economy_fragment(request: HttpRequest) -> HttpResponse:
    """Economy panel: weekly mint/sink/transfer + money-supply stat tiles."""
    supply = money_supply()
    context = {
        "series": [_series_row(s) for s in economy_series()],
        "money_supply": supply,
        "money_supply_display": {key: format_coppers(value) for key, value in supply.items()},
    }
    return render(request, "admin/tuning/_economy_panel.html", context)


@superuser_required
def ops_story_fragment(request: HttpRequest) -> HttpResponse:
    """Story/GM panel: weekly beats/scenes + activity snapshot."""
    context = {
        "series": [_series_row(s) for s in story_series()],
        "snapshot": story_snapshot(),
    }
    return render(request, "admin/tuning/_story_panel.html", context)


@superuser_required
def ops_reports_fragment(request: HttpRequest) -> HttpResponse:
    """Reports panel: open/total counts per player-submissions queue."""
    context = {"buckets": reports_snapshot()}
    return render(request, "admin/tuning/_reports_panel.html", context)


@superuser_required
def ops_tech_fragment(request: HttpRequest) -> HttpResponse:
    """Technical health panel: idmapper RAM, process CPU/RSS, errors, deploy info.

    Admin-triggered on demand (Refresh button) rather than loaded on a timer —
    `collect_tech_health()` walks the idmapper cache with `pympler.asizeof`,
    which can be slow with a large cache. Per-row bar-fill percentages follow
    `_series_row`'s pattern: the max across the top-15 rows is the 100%
    reference, floored at 1 so an empty snapshot doesn't divide by zero.
    """
    health = collect_tech_health()
    byte_values = (approx_bytes for _label, _count, approx_bytes in health.idmapper_top)
    max_bytes = max(byte_values, default=0) or 1
    idmapper_rows = [
        {
            "label": label,
            "count": count,
            "approx_bytes": approx_bytes,
            "pct": round(approx_bytes / max_bytes * 100),
        }
        for label, count, approx_bytes in health.idmapper_top
    ]
    context = {"health": health, "idmapper_rows": idmapper_rows}
    return render(request, "admin/tuning/_tech_panel.html", context)
