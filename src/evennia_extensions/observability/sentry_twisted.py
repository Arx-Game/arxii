"""Forward Evennia's error-level log events to Sentry (#3599).

Evennia's log_err / log_trace (evennia/utils/logger.py) go through Twisted's
logging system, not Python's ``logging``, so Sentry's stdlib logging
integration never sees them. This observer sits on Twisted's global log
publisher and captures error-level events.

log_trace emits a traceback one line per event, all inside the caller's
``except`` block. The observer therefore calls ``capture_exception()`` on
every such line and relies on sentry_sdk's default-on DedupeIntegration,
which drops a repeat capture of the same exception object, to collapse
them into one Sentry event. No state is kept here on purpose.

Events carrying BRIDGE_MARKER come from log_bridge.TwistedLogHandler (Django
records re-emitted into Twisted so they reach server.log). Sentry already
captured those through its stdlib integration, so they are skipped here.

Events carrying ``log_io`` are twistd's captured standard IO and are skipped
for a different reason: their level is a fiction. ``LogBeginner.beginLoggingTo``
redirects the daemons' streams as ``[("stdout", info), ("stderr", error)]``, so
settings.LOGGING's console StreamHandler turns *every* Python log record - INFO
included - into an error-level Twisted event. Forwarding those made each Sentry
send that logged anything on its way out (a urllib3 connection retry, a 429)
produce a fresh error event, which produced another send: an unbounded feedback
loop that pinned the reactor and stopped the Server ever answering on the
2026-09-04 deploy. The level here says which stream a line came from, not how
bad it is, so it is not a level at all.
"""

import sys
from typing import Any

import sentry_sdk
from twisted.logger import LogLevel, formatEvent, globalLogPublisher

from evennia_extensions.observability.log_bridge import BRIDGE_MARKER

SENTRY_LOGGER_TAG = "evennia.twisted"

# The key twisted.logger.LoggingFile stamps on every line it captures from a
# redirected sys.stdout / sys.stderr (it emits format="{log_io}", log_io=line).
CAPTURED_IO_KEY = "log_io"

_FORWARDED_LEVELS = frozenset({LogLevel.error, LogLevel.critical})
_installed = False


def _stamp_logger(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Event processor: set the top-level ``logger`` field Sentry's search/tag
    promotion actually reads (the ``set_tag`` call below only adds a searchable
    tag, not this field)."""
    event["logger"] = SENTRY_LOGGER_TAG
    return event


def sentry_log_observer(event: dict[str, Any]) -> None:
    """Twisted log observer: send error-level events to Sentry."""
    if event.get(BRIDGE_MARKER):
        return
    if CAPTURED_IO_KEY in event:
        return
    if event.get("log_level") not in _FORWARDED_LEVELS:
        return
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("logger", SENTRY_LOGGER_TAG)
        scope.add_event_processor(_stamp_logger)
        failure = event.get("log_failure")
        if failure is not None:
            scope.set_extra("evennia_log_line", formatEvent(event))
            sentry_sdk.capture_exception(
                (failure.type, failure.value, failure.getTracebackObject())
            )
            return
        if sys.exc_info()[1] is not None:
            scope.set_extra("evennia_log_line", formatEvent(event))
            sentry_sdk.capture_exception()
            return
        # Do not fingerprint on event["log_format"]: Evennia's _log() emits
        # every plain log_err with the literal format "{line}", so grouping
        # on the template would merge every unrelated Evennia error into one
        # Sentry issue. Leave Sentry's default message-based grouping.
        sentry_sdk.capture_message(formatEvent(event), level="error")


def install_sentry_log_observer() -> None:
    """Attach the observer to Twisted's global publisher, once."""
    global _installed  # noqa: PLW0603
    if _installed:
        return
    globalLogPublisher.addObserver(sentry_log_observer)
    _installed = True
