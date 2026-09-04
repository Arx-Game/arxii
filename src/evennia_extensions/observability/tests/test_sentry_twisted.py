"""Tests for evennia_extensions.observability.sentry_twisted.

These use a real sentry_sdk client with a function transport (no network) and
only the DedupeIntegration explicitly re-added, so the SDK's default-on
DedupeIntegration behavior is exercised without also installing Django/stdlib
integrations into the shared test process (settings.py's own init, which runs
with no ``integrations=`` override, is what covers "dedupe is on by default
in production").
"""

from typing import Any

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
