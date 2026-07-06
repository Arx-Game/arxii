"""Technical health snapshot for the Game Ops dashboard (#1221 Task 8).

Pure-read process/cache/error telemetry: idmapper cache footprint (via
`evennia_extensions.observability.idmapper_gauge.snapshot()`), this process's
RSS/CPU (via `psutil`), the open (non-terminal) system-error count, and
deploy-identifying env vars (git SHA, whether Sentry is configured). Unlike
the other Ops panels, this one is admin-triggered on demand (see
`ops_views.ops_tech_fragment`) rather than loaded on a timer, since
`idmapper_gauge.snapshot()` walks every cached instance with `pympler.asizeof`
and can be slow with a large cache.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

import psutil

from evennia_extensions.observability import idmapper_gauge
from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.models import SystemErrorReport

_IDMAPPER_TOP_N = 15
_SYSTEM_ERRORS_URL = "/staff/system-errors"


@dataclass(frozen=True)
class TechHealthSnapshot:
    """Point-in-time process/cache/error telemetry for the Technical Health panel."""

    idmapper_top: list[tuple[str, int, int]]  # (model_label, instances, approx_bytes)
    idmapper_total_bytes: int
    process_rss_bytes: int
    process_cpu_percent: float
    open_system_errors: int
    system_errors_url: str
    git_sha: str | None
    sentry_dsn_configured: bool


def _git_sha() -> str | None:
    """Deploy-identifying commit SHA from the environment only — no subprocess calls.

    `GIT_SHA` is checked first, falling back to `SOURCE_COMMIT` (a convention
    used by some PaaS build systems); `None` if neither is set.
    """
    return os.environ.get("GIT_SHA") or os.environ.get("SOURCE_COMMIT") or None


def collect_tech_health() -> TechHealthSnapshot:
    """Assemble a `TechHealthSnapshot` from the idmapper gauge, psutil, and the DB.

    `open_system_errors` reuses the same `SubmissionStatus.OPEN` classification
    as `metrics.reports_snapshot`'s "System Errors" bucket (OPEN is the sole
    non-terminal status; REVIEWED/DISMISSED are both terminal) — kept as a
    single count here since the panel only needs the number and its staff link,
    not the open/total pair a table row wants.
    """
    idmapper_snapshot = idmapper_gauge.snapshot()
    idmapper_total_bytes = sum(approx_bytes for _count, approx_bytes in idmapper_snapshot.values())
    idmapper_rows = (
        (label, count, approx_bytes) for label, (count, approx_bytes) in idmapper_snapshot.items()
    )
    idmapper_top = sorted(idmapper_rows, key=lambda row: row[2], reverse=True)[:_IDMAPPER_TOP_N]

    process = psutil.Process()
    process_rss_bytes = process.memory_info().rss
    process_cpu_percent = process.cpu_percent(interval=0.1)

    open_system_errors = SystemErrorReport.objects.filter(status=SubmissionStatus.OPEN).count()

    return TechHealthSnapshot(
        idmapper_top=idmapper_top,
        idmapper_total_bytes=idmapper_total_bytes,
        process_rss_bytes=process_rss_bytes,
        process_cpu_percent=process_cpu_percent,
        open_system_errors=open_system_errors,
        system_errors_url=_SYSTEM_ERRORS_URL,
        git_sha=_git_sha(),
        sentry_dsn_configured=bool(os.environ.get("SENTRY_DSN")),
    )
