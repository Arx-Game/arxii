"""Tests for evennia_extensions.observability.log_bridge."""

import logging
from typing import Any

from django.test import SimpleTestCase
from twisted.logger import LogLevel, formatEvent, globalLogPublisher


class TwistedLogHandlerTests(SimpleTestCase):
    """Python logging records are re-emitted as marked Twisted events."""

    def setUp(self) -> None:
        from evennia_extensions.observability.log_bridge import TwistedLogHandler

        self.events: list[dict[str, Any]] = []
        self.observer = self.events.append
        globalLogPublisher.addObserver(self.observer)
        self.handler = TwistedLogHandler()
        self.handler.setFormatter(logging.Formatter("[{levelname}] {name}: {message}", style="{"))
        self.logger = logging.getLogger("arxii.test.bridge")
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)

    def tearDown(self) -> None:
        self.logger.removeHandler(self.handler)
        globalLogPublisher.removeObserver(self.observer)

    def _bridged(self) -> list[dict[str, Any]]:
        from evennia_extensions.observability.log_bridge import BRIDGE_MARKER

        return [event for event in self.events if event.get(BRIDGE_MARKER)]

    def test_error_record_becomes_a_marked_error_event_with_the_logger_name(self) -> None:
        self.logger.error("Unhandled API exception in %s", "SomeView")

        bridged = self._bridged()
        self.assertEqual(len(bridged), 1)
        event = bridged[0]
        self.assertEqual(event["log_level"], LogLevel.error)
        self.assertEqual(event["log_namespace"], "arxii.test.bridge")
        self.assertIn("Unhandled API exception in SomeView", formatEvent(event))

    def test_levels_map_onto_twisted_levels(self) -> None:
        self.logger.debug("d")
        self.logger.info("i")
        self.logger.warning("w")
        self.logger.critical("c")

        levels = [event["log_level"] for event in self._bridged()]
        self.assertEqual(levels, [LogLevel.debug, LogLevel.info, LogLevel.warn, LogLevel.critical])

    def test_exception_text_is_included(self) -> None:
        message = "boom"
        try:
            raise RuntimeError(message)
        except RuntimeError:
            self.logger.exception("failed")

        text = formatEvent(self._bridged()[0])
        self.assertIn("RuntimeError: boom", text)

    def test_settings_logging_config_carries_the_bridge(self) -> None:
        from django.conf import settings

        handlers = settings.LOGGING["handlers"]
        self.assertEqual(
            handlers["twisted_bridge"]["class"],
            "evennia_extensions.observability.log_bridge.TwistedLogHandler",
        )
        self.assertIn("twisted_bridge", settings.LOGGING["root"]["handlers"])
        for name in ("django", "django.request", "django.db.backends", "world", "evennia"):
            self.assertIn("twisted_bridge", settings.LOGGING["loggers"][name]["handlers"], name)
