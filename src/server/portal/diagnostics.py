"""Privacy-safe, bounded diagnostics for Portal websocket transports.

The Portal is the only layer that can see WebSocket control frames.  This module
keeps a small structured event window for operational correlation.  It never
accepts cookies, player content, close reasons, or arbitrary registration data.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
import json
import logging
import re
import time
from uuid import uuid4

from django.conf import settings

LOGGER = logging.getLogger("arx.portal.transport")
MAX_CLOSE_CODE = 4999

OPAQUE_ID_RE = re.compile(
    r"^v1-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
CONNECTION_ID_RE = OPAQUE_ID_RE
RUN_ID_RE = OPAQUE_ID_RE
DEFAULT_ENABLED_CHANNELS = frozenset({"alpha", "rehearsal"})
EVENT_KINDS = frozenset(
    {
        "transport_open",
        "websocket_open",
        "authenticated",
        "diagnostic_registration",
        "auto_ping_sent",
        "auto_pong_accepted",
        "ping_received",
        "pong_received",
        "ping_timeout",
        "close_frame_sent",
        "close_frame_received",
        "close_callback",
        "protocol_fail",
        "transport_drop",
        "connection_lost",
        "local_disconnect",
    }
)


def diagnostics_default_enabled(channel: object) -> bool:
    """Return the safe default for an explicit deployment channel."""
    return isinstance(channel, str) and channel.strip().lower() in DEFAULT_ENABLED_CHANNELS


def new_opaque_id() -> str:
    """Return the fixed-format identifier shared with browser diagnostics."""
    return f"v1-{uuid4()}"


def valid_opaque_id(value: object) -> bool:
    """Return whether value is a valid Portal/browser opaque identifier."""
    return isinstance(value, str) and bool(OPAQUE_ID_RE.fullmatch(value))


class PortalDiagnosticStore:
    """Retain only a bounded, redacted window of Portal transport events."""

    def __init__(self) -> None:
        self._events: deque[dict[str, object]] = deque()

    @property
    def max_events(self) -> int:
        """Maximum number of events retained in memory."""
        return max(1, settings.PORTAL_DIAGNOSTICS_MAX_EVENTS)

    @property
    def max_age(self) -> timedelta:
        """Maximum event age retained in memory."""
        return timedelta(seconds=max(1, settings.PORTAL_DIAGNOSTICS_MAX_AGE_SECONDS))

    @property
    def enabled(self) -> bool:
        """Whether diagnostics are enabled for this deployment."""
        return settings.PORTAL_DIAGNOSTICS_ENABLED

    def emit(  # noqa: PLR0913
        self,
        event: str,
        *,
        connection_id: str | None = None,
        run_id: str | None = None,
        close_code: int | None = None,
        clean: bool | None = None,
        category: str | None = None,
        cause: str | None = None,
        registration_attempt: int | None = None,
    ) -> dict[str, object] | None:
        """Record and log one allowlisted event.

        Values are assembled by Portal hooks rather than copied from protocol
        payloads.  The resulting JSON is suitable for a structured log sink.
        """
        if event not in EVENT_KINDS or not self.enabled:
            return None
        now = datetime.now(UTC)
        event_record: dict[str, object] = {
            "event": event,
            "protocol": "websocket",
            "connection_id": connection_id if valid_opaque_id(connection_id) else None,
            "run_id": run_id if valid_opaque_id(run_id) else None,
            "timestamp": now.isoformat(timespec="milliseconds"),
            "monotonic_ns": time.monotonic_ns(),
        }
        if isinstance(close_code, int) and 0 <= close_code <= MAX_CLOSE_CODE:
            event_record["close_code"] = close_code
        if isinstance(clean, bool):
            event_record["clean"] = clean
        if category in {"clean", "transport_loss", "protocol_error", "ping_timeout"}:
            event_record["category"] = category
        if cause in {
            "disconnect",
            "send_close",
            "close_reply",
            "fail",
            "abort",
            "peer_close",
            "connection_lost",
            "invalid_registration",
            "duplicate_registration",
            "registration_rate_limited",
            "registration_accepted",
        }:
            event_record["cause"] = cause
        if isinstance(registration_attempt, int) and registration_attempt >= 1:
            event_record["registration_attempt"] = registration_attempt
        self._prune(now)
        self._events.append(event_record)
        while len(self._events) > self.max_events:
            self._events.popleft()
        LOGGER.info(json.dumps(event_record, sort_keys=True, separators=(",", ":")))
        return dict(event_record)

    def snapshot(self) -> list[dict[str, object]]:
        """Return a copy of currently retained events."""
        self._prune(datetime.now(UTC))
        return [dict(event) for event in self._events]

    def clear(self) -> None:
        """Discard retained events, primarily for tests and controlled rotation."""
        self._events.clear()

    def _prune(self, now: datetime) -> None:
        cutoff = now - self.max_age
        while self._events:
            timestamp = self._events[0].get("timestamp")
            if not isinstance(timestamp, str):
                self._events.popleft()
                continue
            try:
                event_time = datetime.fromisoformat(timestamp)
            except ValueError:
                self._events.popleft()
                continue
            if event_time >= cutoff:
                break
            self._events.popleft()


portal_diagnostics = PortalDiagnosticStore()
