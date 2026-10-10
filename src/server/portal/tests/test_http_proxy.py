"""Exercise real Twisted requests across downstream disconnects."""

from django.test import SimpleTestCase
from twisted.internet.error import ConnectionLost
from twisted.internet.testing import StringTransport
from twisted.python.failure import Failure
from twisted.web.http import HTTPChannel
from twisted.web.resource import Resource
from twisted.web.server import Request, Site

from server.conf.web_plugins import at_webproxy_root_creation
from server.portal.http_proxy import DisconnectAwareProxyFactory, DisconnectAwareProxyResource


class HttpProxyTests(SimpleTestCase):
    """A late upstream response must never finish a lost downstream request."""

    def setUp(self):
        self.channel = HTTPChannel()
        self.channel.site = Site(Resource())
        self.channel.makeConnection(StringTransport())
        self.request = Request(self.channel)
        self.request.method = b"GET"
        self.request.clientproto = b"HTTP/1.1"
        self.factory = DisconnectAwareProxyFactory(b"GET", b"/", b"HTTP/1.1", {}, b"", self.request)
        self.protocol = self.factory.buildProtocol(None)
        self.protocol.makeConnection(StringTransport())

    def test_late_response_after_disconnect_closes_upstream(self):
        self.request.connectionLost(Failure(ConnectionLost()))
        self.protocol.handleResponsePart(b"late body")
        self.protocol.handleResponseEnd()
        self.assertFalse(self.request.finished)
        self.assertTrue(self.protocol.transport.disconnecting)

    def test_disconnect_before_upstream_connection_failure(self):
        self.request.connectionLost(Failure(ConnectionLost()))
        self.factory.clientConnectionFailed(None, Failure(ConnectionLost()))
        self.assertFalse(self.request.finished)

    def test_live_upstream_failure_returns_gateway_error(self):
        self.channel.requests.append(self.request)
        self.factory.clientConnectionFailed(None, Failure(ConnectionLost()))
        self.assertTrue(self.request.finished)
        self.assertEqual(self.request.code, 501)

    def test_live_response_is_finished(self):
        self.channel.requests.append(self.request)
        self.protocol.handleStatus(b"HTTP/1.1", b"200", b"OK")
        self.protocol.handleResponsePart(b"body")
        self.protocol.handleResponseEnd()
        self.assertTrue(self.request.finished)
        self.assertTrue(self.protocol.transport.disconnecting)

    def test_hook_preserves_registered_children_and_nested_factory(self):
        root = DisconnectAwareProxyResource("127.0.0.1", 4005, "")
        child = DisconnectAwareProxyResource("127.0.0.1", 4005, "/special")
        root.putChild(b"special", child)
        installed = at_webproxy_root_creation(root)
        self.assertIs(installed.children[b"special"], child)
        nested = installed.getChild(b"api", self.request).getChild(b"health", self.request)
        self.assertEqual(nested.path, "/api/health")
        self.assertIs(nested.proxyClientFactoryClass, DisconnectAwareProxyFactory)
