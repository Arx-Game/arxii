"""Service functions for scheduled-downtime announcements (#3194).

``get_next_downtime`` merges two sources into one answer:

- the next staff-declared ``DowntimeWindow`` that has not been canceled and
  has not already finished, and
- the host's own scheduled reboot, read live from systemd's
  scheduled-shutdown file (written by ``shutdown -r``/unattended-upgrades
  the moment the reboot is scheduled — 22 hours ahead in the 2026-08-16
  incident). Deriving it here means the reboot warning exists without anyone
  typing it, and disappears by itself if the reboot is canceled.
"""

from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from world.downtime.constants import (
    SYSTEM_REBOOT_DURATION_MINUTES,
    SYSTEM_REBOOT_MESSAGE,
    DowntimeSource,
)
from world.downtime.models import DowntimeWindow
from world.downtime.types import PlannedDowntime

logger = logging.getLogger(__name__)


def _scheduled_shutdown_file() -> Path:
    # settings.SCHEDULED_SHUTDOWN_FILE: systemd's scheduled-shutdown sentinel,
    # overridable for tests and non-systemd hosts.
    return Path(settings.SCHEDULED_SHUTDOWN_FILE)


def _next_staff_window(now: datetime) -> PlannedDowntime | None:
    # The 48h lookback keeps the scan bounded while still catching a window
    # that started in the past and is still in progress; a single window is
    # never realistically longer than that.
    windows = DowntimeWindow.objects.filter(
        canceled_at__isnull=True,
        starts_at__gte=now - timedelta(hours=48),
    ).order_by("starts_at")
    for window in windows:
        ends_at = window.starts_at + timedelta(minutes=window.expected_duration_minutes)
        if ends_at >= now:
            return PlannedDowntime(
                source=DowntimeSource.STAFF,
                starts_at=window.starts_at,
                expected_duration_minutes=window.expected_duration_minutes,
                message=window.message,
            )
    return None


def _system_scheduled_reboot(now: datetime) -> PlannedDowntime | None:
    """Parse systemd's scheduled-shutdown file into a derived downtime window.

    The file is ``KEY=VALUE`` lines; ``USEC`` is the scheduled time in
    microseconds since the epoch and ``MODE`` is the shutdown kind. Any parse
    problem returns None — a broken warning must never break the status API.
    """
    path = _scheduled_shutdown_file()
    try:
        content = path.read_text()
    except OSError:
        return None

    fields = {}
    for line in content.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip()

    usec = fields.get("USEC")
    if not usec or not usec.isdigit():
        return None

    starts_at = datetime.fromtimestamp(int(usec) / 1_000_000, tz=UTC)
    ends_at = starts_at + timedelta(minutes=SYSTEM_REBOOT_DURATION_MINUTES)
    if ends_at < now:
        # A stale file for a shutdown that already happened.
        return None

    return PlannedDowntime(
        source=DowntimeSource.SYSTEM,
        starts_at=starts_at,
        expected_duration_minutes=SYSTEM_REBOOT_DURATION_MINUTES,
        message=SYSTEM_REBOOT_MESSAGE,
    )


def get_next_downtime() -> PlannedDowntime | None:
    """Return the soonest upcoming (or in-progress) downtime, if any."""
    now = timezone.now()
    candidates = [
        candidate
        for candidate in (_next_staff_window(now), _system_scheduled_reboot(now))
        if candidate is not None
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate.starts_at)
