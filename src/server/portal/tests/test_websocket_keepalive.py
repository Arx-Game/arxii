"""The websocket keepalive that stops an idle session re-logging in every 127s (#3745).

Measured against production on 2026-09-12, two samples from separate Cloudflare
edges: an idle `wss://` connection to `/ws/game/` is closed at 125.613s and
125.595s by a bare TCP FIN with no websocket close frame. The browser reports
that as close code 1006, the SPA's abnormal-close path reconnects a second
later, and the reconnect carries the stored autologin uid straight back into
`ServerSessionHandler.portal_connect` -> `login(..., force=True)`. A third
sample that sent a ping every 30s stayed open for the full 420s window, so the
timeout is an idle timer that any frame resets - which is what these tests pin.
"""

from autobahn.twisted.websocket import WebSocketServerFactory
from django.conf import settings
from django.test import SimpleTestCase

from server.portal.secure_websocket import SecureWebSocketClient

# The measured close, rounded down. Every margin below is stated against it
# rather than against a made-up round number, so re-tuning the interval has to
# argue with the measurement.
EDGE_IDLE_CLOSE_SECONDS = 125.5


class WebSocketAutoPingTests(SimpleTestCase):
    """Autobahn's auto-ping has to be on, and has to fit under the edge timeout."""

    def _connected_protocol(self) -> SecureWebSocketClient:
        """A protocol instance past the point where autobahn copies factory options."""
        protocol = SecureWebSocketClient()
        protocol.factory = WebSocketServerFactory()
        protocol._connectionMade()
        return protocol

    def test_factory_default_leaves_autoping_off(self):
        """Why the protocol class has to carry this at all.

        Evennia builds the `WebSocketServerFactory` itself
        (`evennia/server/portal/service.py`) and never calls
        `setProtocolOptions`, so nothing in the chain keeps an idle connection
        warm unless the protocol class sets it.
        """
        self.assertEqual(WebSocketServerFactory().autoPingInterval, 0)

    def test_autoping_interval_survives_the_factory_option_copy(self):
        """`_connectionMade` copies factory options onto the instance.

        It copies only attributes the instance does not already have, so a class
        attribute wins over the factory's 0. Move the assignment anywhere that
        runs later and the factory default silently wins instead.
        """
        self.assertEqual(
            self._connected_protocol().autoPingInterval,
            settings.WEBSOCKET_AUTOPING_INTERVAL,
        )

    def test_two_intervals_fit_inside_the_edge_idle_timeout(self):
        """One dropped ping must not cost the connection."""
        protocol = self._connected_protocol()
        self.assertGreater(protocol.autoPingInterval, 0)
        self.assertLess(protocol.autoPingInterval * 2, EDGE_IDLE_CLOSE_SECONDS)

    def test_unanswered_ping_drops_the_link_before_the_edge_does(self):
        """A half-open link is ours to notice, not the edge's.

        With `autoPingTimeout` set, autobahn drops a connection whose pong never
        arrives; the session then disconnects through Evennia's own path instead
        of dying as a bare FIN the server never hears about.
        """
        protocol = self._connected_protocol()
        self.assertGreater(protocol.autoPingTimeout, 0)
        self.assertLess(
            protocol.autoPingInterval + protocol.autoPingTimeout,
            EDGE_IDLE_CLOSE_SECONDS,
        )
