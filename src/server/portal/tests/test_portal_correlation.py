"""Focused tests for the Portal transport correlation boundary."""

import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from evennia.server.portal.webclient import WebSocketClient

from server.portal.diagnostics import (
    CONNECTION_ID_RE,
    PortalDiagnosticStore,
    diagnostics_default_enabled,
    portal_diagnostics,
)
from server.portal.secure_websocket import (
    DIAGNOSTIC_ACK,
    DIAGNOSTIC_REGISTER,
    SecureWebSocketClient,
)


@override_settings(PORTAL_DIAGNOSTICS_ENABLED=True)
class PortalCorrelationTests(SimpleTestCase):
    """Registration is Portal control traffic, not a game input."""

    def setUp(self):
        portal_diagnostics.clear()

    def tearDown(self):
        portal_diagnostics.clear()

    def _protocol(self):
        protocol = SecureWebSocketClient()
        with patch.object(WebSocketClient, "_connectionMade"):
            protocol._connectionMade()
        return protocol

    def test_transport_open_assigns_opaque_connection_id(self):
        protocol = self._protocol()

        self.assertRegex(protocol.portal_connection_id, CONNECTION_ID_RE)
        self.assertEqual(portal_diagnostics.snapshot()[0]["event"], "transport_open")

    def test_valid_registration_is_acknowledged_and_never_reaches_server(self):
        protocol = self._protocol()
        frame = json.dumps(
            [DIAGNOSTIC_REGISTER, [], {"run_id": "v1-12345678-1234-4234-8234-123456789abc"}]
        ).encode()

        with (
            patch.object(protocol, "sendLine") as send_line,
            patch.object(WebSocketClient, "onMessage") as server_message,
        ):
            protocol.onMessage(frame, False)

        server_message.assert_not_called()
        send_line.assert_called_once()
        ack = json.loads(send_line.call_args.args[0])
        self.assertEqual(
            ack, [DIAGNOSTIC_ACK, [], {"connection_id": protocol.portal_connection_id}]
        )
        self.assertEqual(
            protocol.portal_diagnostic_run_id, "v1-12345678-1234-4234-8234-123456789abc"
        )

    def test_invalid_duplicate_and_rate_limited_registration_are_consumed(self):
        protocol = self._protocol()
        invalid = json.dumps([DIAGNOSTIC_REGISTER, [], {"run_id": "cookie-or-account"}]).encode()
        duplicate = json.dumps(
            [DIAGNOSTIC_REGISTER, [], {"run_id": "v1-12345678-1234-4234-8234-123456789abc"}]
        ).encode()

        with (
            patch.object(protocol, "sendLine"),
            patch.object(WebSocketClient, "onMessage") as server_message,
        ):
            protocol.onMessage(invalid, False)
            protocol.onMessage(duplicate, False)
            for _ in range(3):
                protocol.onMessage(invalid, False)

        server_message.assert_not_called()
        self.assertEqual(
            protocol.portal_diagnostic_run_id,
            "v1-12345678-1234-4234-8234-123456789abc",
        )
        causes = [event.get("cause") for event in portal_diagnostics.snapshot()]
        self.assertIn("invalid_registration", causes)
        self.assertIn("registration_rate_limited", causes)

    def test_registration_ack_contains_no_run_id_or_sensitive_fields(self):
        protocol = self._protocol()
        run_id = "v1-12345678-1234-4234-8234-123456789abc"

        with patch.object(protocol, "sendLine") as send_line:
            protocol.onMessage(
                json.dumps([DIAGNOSTIC_REGISTER, [], {"run_id": run_id}]).encode(), False
            )

        self.assertNotIn(run_id, send_line.call_args.args[0])
        self.assertNotIn("cookie", send_line.call_args.args[0])
        self.assertNotIn("reason", json.dumps(portal_diagnostics.snapshot()))

    def test_lifecycle_events_redact_close_reason_and_retention_is_bounded(self):
        protocol = self._protocol()
        with patch.object(WebSocketClient, "onClose"):
            protocol.onClose(False, 1006, "cookie=secret player prose")
        event = portal_diagnostics.snapshot()[-1]
        self.assertEqual(event["event"], "close_callback")
        serialized = json.dumps(portal_diagnostics.snapshot())
        self.assertNotIn("cookie", serialized)
        self.assertNotIn("player prose", serialized)

    @override_settings(PORTAL_DIAGNOSTICS_MAX_EVENTS=2)
    def test_event_retention_has_a_hard_count_bound(self):
        for _ in range(4):
            portal_diagnostics.emit("transport_open")

        events = portal_diagnostics.snapshot()
        self.assertLessEqual(len(events), 2)
        self.assertEqual(events[-1]["event"], "transport_open")

    def test_channel_defaults_are_safe_and_explicit_override_wins(self):
        self.assertFalse(diagnostics_default_enabled("production"))
        self.assertFalse(diagnostics_default_enabled("development"))
        self.assertTrue(diagnostics_default_enabled("alpha"))
        self.assertTrue(diagnostics_default_enabled("rehearsal"))
        with override_settings(PORTAL_DIAGNOSTICS_ENABLED=False):
            self.assertFalse(PortalDiagnosticStore().enabled)
        with override_settings(PORTAL_DIAGNOSTICS_ENABLED=True):
            self.assertTrue(PortalDiagnosticStore().enabled)

    def test_unknown_event_kind_is_rejected(self):
        self.assertIsNone(portal_diagnostics.emit("not_allowlisted"))
        self.assertEqual(portal_diagnostics.snapshot(), [])
