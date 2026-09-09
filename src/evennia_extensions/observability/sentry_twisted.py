"""Forward Evennia's error-level log events to Sentry (#3599).

Evennia's log_err / log_trace (evennia/utils/logger.py) go through Twisted's
logging system, not Python's ``logging``, so Sentry's stdlib logging
integration never sees them. This observer sits on Twisted's global log
publisher and captures error-level events.

**One logical error log call must produce one Sentry event.** Evennia's
``_log`` splits whatever string it is handed on newlines and calls the log
function once per line, so a traceback arrives here as N separate error
events rather than one. Two front doors do this:

- ``log_trace()`` formats the *current* traceback and passes the whole thing;
- ``log_err()`` is routinely handed an already-formatted traceback as text -
  ``amp.py:489``'s ``"AMP Error from {info}: {trcbck} {err}"`` is the one that
  matters most here, because it is how a Server-side exception is reported on
  the Portal side.

When a live exception is in flight the ``capture_exception`` branches below
handle that: sentry_sdk's default-on DedupeIntegration drops a repeat capture
of the same exception object, collapsing the lines into one event. **That
does not help the relayed case.** A traceback that crossed the AMP boundary is
just text on this side, ``sys.exc_info()`` is empty, and every line took the
``capture_message`` branch as a distinct message - so Sentry grouped each line
as its own issue. On 2026-09-09 one broken login (517 occurrences) became
5,740 events across 11 issues and consumed the entire monthly quota in 19
hours (digest #3736). ``_TracebackBurst`` below is what closes that: it reassembles
the lines of a relayed traceback into a single event.

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

import contextlib
import sys
from typing import Any

import sentry_sdk
from twisted.logger import LogLevel, formatEvent, globalLogPublisher

from evennia_extensions.observability.log_bridge import BRIDGE_MARKER

SENTRY_LOGGER_TAG = "evennia.twisted"

# The key twisted.logger.LoggingFile stamps on every line it captures from a
# redirected sys.stdout / sys.stderr (it emits format="{log_io}", log_io=line).
CAPTURED_IO_KEY = "log_io"

# CPython's first line of any formatted traceback. Both format_exc() (log_trace)
# and Failure.getTraceback() (the AMP relay) emit it, so it is the reliable
# "a multi-line burst starts here" marker.
TRACEBACK_HEADER = "Traceback (most recent call last):"

# A runaway or malformed traceback must not grow without bound.
MAX_BURST_LINES = 200

_FORWARDED_LEVELS = frozenset({LogLevel.error, LogLevel.critical})
_installed = False


def _stamp_logger(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Event processor: set the top-level ``logger`` field Sentry's search/tag
    promotion actually reads (the ``set_tag`` call below only adds a searchable
    tag, not this field)."""
    event["logger"] = SENTRY_LOGGER_TAG
    return event


def _send(message: str, detail: str) -> None:
    """Send one error-level message event, carrying ``detail`` as context."""
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("logger", SENTRY_LOGGER_TAG)
        scope.add_event_processor(_stamp_logger)
        scope.set_extra("evennia_log_line", detail)
        sentry_sdk.capture_message(message, level="error")


class _TracebackBurst:
    """Reassembles the per-line events of one relayed traceback.

    A formatted traceback is self-delimiting, which is what lets this work
    without guessing at timing: it opens with :data:`TRACEBACK_HEADER`, its
    frames are indented, and it closes with an unindented ``ExcType: message``
    line. So the burst ends on its own terminator, and lines that are not part
    of a traceback never enter the buffer at all - an ordinary single-line
    ``log_err`` is sent immediately, exactly as before.

    A chained traceback ("During handling of the above exception...") ends the
    first burst at that unindented line and opens a second one at the next
    header. Two events for two exceptions is the right answer anyway.
    """

    def __init__(self) -> None:
        self._lines: list[str] = []

    @property
    def pending(self) -> bool:
        return bool(self._lines)

    def accepts(self, line: str) -> bool:
        """Is ``line`` part of a traceback burst (either opening or continuing one)."""
        if self._lines:
            return True
        return TRACEBACK_HEADER in line

    def add(self, line: str) -> None:
        """Buffer ``line``; flush if it terminates the traceback or overruns the cap."""
        self._lines.append(line)
        # The header itself is unindented, so it can never be the terminator.
        is_terminator = len(self._lines) > 1 and line.strip() and not line[:1].isspace()
        if is_terminator or len(self._lines) >= MAX_BURST_LINES:
            self.flush()

    def flush(self) -> None:
        """Emit the buffered lines as a single Sentry event.

        Titled by the **last** non-empty line - the ``ExcType: message`` one.
        Titling by the first line would put every traceback under the identical
        ``Traceback (most recent call last):`` heading and merge every unrelated
        Evennia error into one Sentry issue, the same trap the single-line path
        avoids by not fingerprinting on ``log_format``.
        """
        if not self._lines:
            return
        lines, self._lines = self._lines, []
        text = "\n".join(lines)
        title = next((line for line in reversed(lines) if line.strip()), text)
        _send(title, text)


_burst = _TracebackBurst()


def _schedule_flush() -> None:
    """Drain a stranded partial burst at the end of this reactor turn.

    Only reachable when a traceback never delivered its unindented terminator
    line - a relay truncated mid-frame.

    With no reactor to defer to (startup, shutdown, a test process) this does
    nothing and the burst stays buffered. Flushing inline here instead would
    fire after the *first* line, before the traceback's remaining lines have
    arrived, which is the per-line fan-out this whole module exists to stop.
    A held burst is not a lost one: the next error line to arrive closes it.
    """
    from twisted.internet import reactor  # noqa: PLC0415 - defer installing a reactor

    if reactor.running:
        reactor.callLater(0, _burst.flush)


def sentry_log_observer(event: dict[str, Any]) -> None:
    """Twisted log observer: send error-level events to Sentry."""
    if event.get(BRIDGE_MARKER):
        return
    if CAPTURED_IO_KEY in event:
        return
    if event.get("log_level") not in _FORWARDED_LEVELS:
        return
    # Swallowed on purpose, and NOT logged: anything logged from inside a log
    # observer re-enters this observer, which is the feedback shape that took
    # production down on 2026-09-04. Twisted also disables an observer that
    # raises, which would silently end Sentry reporting for the whole process.
    with contextlib.suppress(Exception):
        _forward(event)


def _forward(event: dict[str, Any]) -> None:
    failure = event.get("log_failure")
    if failure is not None:
        _burst.flush()
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("logger", SENTRY_LOGGER_TAG)
            scope.add_event_processor(_stamp_logger)
            scope.set_extra("evennia_log_line", formatEvent(event))
            sentry_sdk.capture_exception(
                (failure.type, failure.value, failure.getTracebackObject())
            )
        return
    if sys.exc_info()[1] is not None:
        # A live exception beats any reconstruction: Sentry gets real frames,
        # and DedupeIntegration collapses log_trace's per-line repeats for us.
        _burst.flush()
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("logger", SENTRY_LOGGER_TAG)
            scope.add_event_processor(_stamp_logger)
            scope.set_extra("evennia_log_line", formatEvent(event))
            sentry_sdk.capture_exception()
        return

    line = formatEvent(event)
    if _burst.accepts(line):
        _burst.add(line)
        if _burst.pending:
            _schedule_flush()
        return
    # Not part of a traceback: send as its own event, and never fingerprint on
    # event["log_format"] - Evennia's _log() emits every plain log_err with the
    # literal format "{line}", so grouping on the template would merge every
    # unrelated Evennia error into one Sentry issue. Sentry's default
    # message-based grouping is what we want.
    _burst.flush()
    _send(line, line)


def install_sentry_log_observer() -> None:
    """Attach the observer to Twisted's global publisher, once."""
    global _installed  # noqa: PLW0603
    if _installed:
        return
    globalLogPublisher.addObserver(sentry_log_observer)
    _installed = True
