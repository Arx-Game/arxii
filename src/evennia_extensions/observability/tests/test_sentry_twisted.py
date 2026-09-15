"""Tests for evennia_extensions.observability.sentry_twisted.

These use a real sentry_sdk client with a function transport (no network) and
only the DedupeIntegration explicitly re-added, so the SDK's default-on
DedupeIntegration behavior is exercised without also installing Django/stdlib
integrations into the shared test process (settings.py's own init, which runs
with no ``integrations=`` override, is what covers "dedupe is on by default
in production").
"""

from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase
import sentry_sdk
from sentry_sdk.integrations.dedupe import DedupeIntegration
from twisted.logger import Logger, LoggingFile, LogLevel, globalLogPublisher

FAKE_DSN = "https://examplePublicKey@o0.ingest.sentry.invalid/0"


class SentryObserverTests(SimpleTestCase):
    """Error-level Twisted events reach Sentry once; everything else does not."""

    def setUp(self) -> None:
        from evennia_extensions.observability.sentry_twisted import sentry_log_observer

        self.events: list[dict[str, Any]] = []
        sentry_sdk.init(
            dsn=FAKE_DSN,
            transport=self.events.append,
            default_integrations=False,
            integrations=[DedupeIntegration()],
        )
        self.observer = sentry_log_observer
        globalLogPublisher.addObserver(self.observer)

    def tearDown(self) -> None:
        globalLogPublisher.removeObserver(self.observer)
        sentry_sdk.get_global_scope().set_client(None)

    def test_log_trace_inside_except_sends_exactly_one_exception_event(self) -> None:
        from evennia.utils import logger as evennia_logger

        error_message = "account row loaded as the bare AccountDB"
        try:
            raise ValueError(error_message)
        except ValueError:
            evennia_logger.log_trace("while loading the account")

        self.assertEqual(len(self.events), 1)
        exception = self.events[0]["exception"]["values"][0]
        self.assertEqual(exception["type"], "ValueError")
        self.assertEqual(self.events[0]["tags"]["logger"], "evennia.twisted")
        self.assertEqual(self.events[0]["logger"], "evennia.twisted")
        self.assertTrue(self.events[0]["extra"]["evennia_log_line"])

    def test_log_err_without_an_active_exception_sends_one_message(self) -> None:
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err("portal lost its server connection")

        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["level"], "error")
        self.assertIn("portal lost its server connection", self.events[0]["message"])
        self.assertEqual(self.events[0]["logger"], "evennia.twisted")

    def test_twisted_failure_event_sends_the_failure_as_an_exception(self) -> None:
        log = Logger(namespace="test.failure")
        error_message = "missing"
        try:
            raise KeyError(error_message)
        except KeyError:
            log.failure("deferred blew up", level=LogLevel.error)

        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["exception"]["values"][0]["type"], "KeyError")

    def test_info_and_warning_events_are_not_forwarded(self) -> None:
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_info("server started")
        evennia_logger.log_warn("slow tick")

        self.assertEqual(self.events, [])

    def test_twistd_captured_stderr_is_not_forwarded(self) -> None:
        """twistd redirects sys.stderr into Twisted's log at ERROR level.

        LogBeginner.beginLoggingTo maps ``[("stdout", info), ("stderr", error)]``,
        so settings.LOGGING's console StreamHandler turns every Python log
        record - INFO and WARNING included - into an error-level Twisted event
        once the daemons are running. Forwarding those to Sentry made each
        failed/throttled Sentry send emit another urllib3 warning, which became
        another error event: the unbounded feedback loop that stopped the Server
        answering on the 2026-09-04 deploy. Captured standard IO carries
        ``log_io``; its level says which stream it came from, not how bad it is.
        """
        stderr = LoggingFile(logger=Logger(namespace="stderr"), level=LogLevel.error)

        stderr.write("[INFO] world.game_clock.scheduler GameTickScript already exists\n")
        stderr.write("[WARNING] urllib3.connectionpool Retrying after connection broken\n")

        self.assertEqual(self.events, [])

    def test_bridged_django_records_are_skipped(self) -> None:
        from evennia_extensions.observability.sentry_twisted import BRIDGE_MARKER

        log = Logger(namespace="django.request")
        log.error("Unhandled API exception", **{BRIDGE_MARKER: True})

        self.assertEqual(self.events, [])


class InstallTests(SimpleTestCase):
    """install_sentry_log_observer registers the observer exactly once."""

    def test_install_is_idempotent(self) -> None:
        from evennia_extensions.observability import sentry_twisted

        before = len(globalLogPublisher._observers)
        sentry_twisted.install_sentry_log_observer()
        sentry_twisted.install_sentry_log_observer()
        try:
            self.assertEqual(len(globalLogPublisher._observers), before + 1)
        finally:
            globalLogPublisher.removeObserver(sentry_twisted.sentry_log_observer)
            sentry_twisted._installed = False


class MultiLineBurstTests(SimpleTestCase):
    """One logical Evennia error log call is one Sentry event, not one per line.

    Evennia's ``_log`` (evennia/utils/logger.py) splits whatever string it is
    given on newlines and calls the log function **once per line**
    (``for line in msg.splitlines(): logfunc("{line}", ...)``). Both of the
    error-logging front doors go through it:

    - ``log_trace()`` formats the current traceback and passes the whole thing,
    - ``log_err()`` is routinely handed an already-formatted traceback, e.g.
      ``amp.py:489``'s ``"AMP Error from {info}: {trcbck} {err}"``.

    So a single AMP failure arrived at the observer as ~11 separate error
    events. Each took the ``capture_message`` branch (no live exception is in
    flight - the traceback is text relayed across the AMP boundary), and each
    line is a different message string, so Sentry grouped every one as its own
    issue. On 2026-09-09 that turned 517 failed logins into 5,740 events and
    consumed the whole monthly quota in 19 hours (digest #3736).
    """

    def setUp(self) -> None:
        from twisted.internet.task import Clock

        from evennia_extensions.observability.sentry_twisted import sentry_log_observer

        self.events: list[dict[str, Any]] = []
        sentry_sdk.init(
            dsn=FAKE_DSN,
            transport=self.events.append,
            default_integrations=False,
            integrations=[DedupeIntegration()],
        )
        # A Clock stands in for the global reactor: the observer buffers a burst
        # and flushes it at the end of the current reactor turn, which is what
        # makes "the lines of one _log call" a well-defined group.
        self.clock = Clock()
        self.clock.running = True
        patcher = patch("twisted.internet.reactor", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.observer = sentry_log_observer
        globalLogPublisher.addObserver(self.observer)

    def tearDown(self) -> None:
        globalLogPublisher.removeObserver(self.observer)
        sentry_sdk.get_global_scope().set_client(None)

    def _turn(self) -> None:
        """Let the reactor reach the end of its current iteration."""
        self.clock.advance(0)

    def test_multi_line_log_err_sends_one_event_not_one_per_line(self) -> None:
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err(
            "AMP Error from AdminPortal2Server: Traceback (most recent call last):\n"
            '  File "/opt/arxii/releases/main/src/typeclasses/accounts.py", line 494, '
            "in at_post_login\n"
            "    session.at_login()\n"
            "TypeError: ServerSession.at_login() missing 1 required positional "
            "argument: 'account'"
        )
        self._turn()

        self.assertEqual(len(self.events), 1)

    def test_burst_is_titled_by_its_last_line_so_tracebacks_stay_distinct(self) -> None:
        """Group on the exception line, never the ``Traceback ...`` header.

        Every traceback starts with the same first line, so titling a burst by
        its first line would merge every unrelated Evennia error into a single
        Sentry issue - the same trap the single-line branch avoids by not
        fingerprinting on ``log_format``.
        """
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err(
            "Traceback (most recent call last):\n"
            '  File "a.py", line 1, in f\n'
            "TypeError: at_login() missing 1 required positional argument"
        )
        self._turn()
        evennia_logger.log_err(
            "Traceback (most recent call last):\n"
            '  File "b.py", line 2, in g\n'
            "FieldError: Unsupported lookup 'id__exact' for ForeignKey"
        )
        self._turn()

        self.assertEqual(len(self.events), 2)
        messages = [event["message"] for event in self.events]
        self.assertIn("TypeError: at_login() missing 1 required positional argument", messages[0])
        self.assertIn("FieldError: Unsupported lookup 'id__exact' for ForeignKey", messages[1])

    def test_the_whole_burst_is_kept_on_the_event(self) -> None:
        """The frames are the diagnostic value - titling by one line must not lose them."""
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err(
            "Traceback (most recent call last):\n"
            '  File "/opt/arxii/src/typeclasses/accounts.py", line 494, in at_post_login\n'
            "TypeError: at_login() missing 1 required positional argument"
        )
        self._turn()

        self.assertEqual(len(self.events), 1)
        captured = self.events[0]["extra"]["evennia_log_line"]
        self.assertIn("accounts.py", captured)
        self.assertIn("at_post_login", captured)
        self.assertIn("Traceback (most recent call last):", captured)

    def test_two_separate_single_line_errors_stay_two_events(self) -> None:
        """Coalescing is per reactor turn, not a blanket dedupe of error lines."""
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err("portal lost its server connection")
        self._turn()
        evennia_logger.log_err("portal regained its server connection")
        self._turn()

        self.assertEqual(len(self.events), 2)

    def test_a_truncated_traceback_is_still_reported_at_the_end_of_the_turn(self) -> None:
        """A relay cut off mid-frame never sends its terminator line.

        The burst has no unindented ``ExcType: message`` to close on, so it
        would sit in the buffer forever. The reactor backstop drains it at the
        end of the turn: reported late beats not reported.
        """
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err(
            "Traceback (most recent call last):\n"
            '  File "/opt/arxii/src/typeclasses/accounts.py", line 494, in at_post_login\n'
            "    session.at_login()"
        )
        self.assertEqual(self.events, [], "no terminator yet, so nothing should have been sent")

        self._turn()

        self.assertEqual(len(self.events), 1)
        self.assertIn("at_post_login", self.events[0]["extra"]["evennia_log_line"])

    def test_a_live_exception_still_reports_as_an_exception(self) -> None:
        """The rich path wins: a real traceback object beats a reconstructed string."""
        from evennia.utils import logger as evennia_logger

        error_message = "account row loaded as the bare AccountDB"
        try:
            raise ValueError(error_message)
        except ValueError:
            evennia_logger.log_trace("while loading the account")
        self._turn()

        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["exception"]["values"][0]["type"], "ValueError")


class BurstWithoutAReactorTests(SimpleTestCase):
    """No running reactor (startup, shutdown, tests) must never lose an error."""

    def setUp(self) -> None:
        from evennia_extensions.observability.sentry_twisted import sentry_log_observer

        self.events: list[dict[str, Any]] = []
        sentry_sdk.init(
            dsn=FAKE_DSN,
            transport=self.events.append,
            default_integrations=False,
            integrations=[DedupeIntegration()],
        )
        self.observer = sentry_log_observer
        globalLogPublisher.addObserver(self.observer)

    def tearDown(self) -> None:
        globalLogPublisher.removeObserver(self.observer)
        sentry_sdk.get_global_scope().set_client(None)

    def test_error_is_still_reported_when_nothing_can_schedule_a_flush(self) -> None:
        """Degrades to the old line-at-a-time behavior rather than dropping the error.

        Losing an error entirely is strictly worse than reporting it noisily, so
        the fallback when no flush can be scheduled is to send inline.
        """
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err("portal lost its server connection")

        self.assertEqual(len(self.events), 1)
        self.assertIn("portal lost its server connection", self.events[0]["message"])

    def test_a_truncated_traceback_is_held_then_closed_by_the_next_error(self) -> None:
        """Held, not dropped, and never split back into one event per line.

        With no reactor there is nothing to defer a flush to. Sending inline
        after each line would fire before the rest of the traceback arrived,
        recreating the per-line fan-out. So the burst waits, and the next error
        line closes it - one event, still carrying its frames.
        """
        from evennia.utils import logger as evennia_logger

        evennia_logger.log_err(
            "Traceback (most recent call last):\n"
            '  File "/opt/arxii/src/typeclasses/accounts.py", line 494, in at_post_login'
        )
        self.assertEqual(self.events, [], "a partial traceback should not send per line")

        evennia_logger.log_err("portal lost its server connection")

        self.assertEqual(len(self.events), 1)
        self.assertIn("at_post_login", self.events[0]["extra"]["evennia_log_line"])
