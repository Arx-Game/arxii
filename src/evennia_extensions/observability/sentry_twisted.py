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
"""

import sys
from typing import Any

import sentry_sdk
from twisted.logger import LogLevel, formatEvent, globalLogPublisher

BRIDGE_MARKER = "arxii_bridged"
SENTRY_LOGGER_TAG = "evennia.twisted"

_FORWARDED_LEVELS = frozenset({LogLevel.error, LogLevel.critical})
_installed = False


def sentry_log_observer(event: dict[str, Any]) -> None:
    """Twisted log observer: send error-level events to Sentry."""
    if event.get(BRIDGE_MARKER):
        return
    if event.get("log_level") not in _FORWARDED_LEVELS:
        return
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("logger", SENTRY_LOGGER_TAG)
        failure = event.get("log_failure")
        if failure is not None:
            sentry_sdk.capture_exception(
                (failure.type, failure.value, failure.getTracebackObject())
            )
            return
        if sys.exc_info()[1] is not None:
            sentry_sdk.capture_exception()
            return
        sentry_sdk.capture_message(formatEvent(event), level="error")


def install_sentry_log_observer() -> None:
    """Attach the observer to Twisted's global publisher, once."""
    global _installed  # noqa: PLW0603
    if _installed:
        return
    globalLogPublisher.addObserver(sentry_log_observer)
    _installed = True
