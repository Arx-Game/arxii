"""Typed return shapes for the downtime services (#3194)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PlannedDowntime:
    """The next window the game expects to be unavailable.

    ``source`` is a ``DowntimeSource`` value: a staff-declared window or the
    host's own scheduled reboot.
    """

    source: str
    starts_at: datetime
    expected_duration_minutes: int
    message: str
