"""Portal HTTP proxy lifecycle tied to the downstream request."""

# ruff: noqa: N802, N815 -- Twisted extension API names.

from urllib.parse import quote

from evennia.server.webserver import EvenniaReverseProxyResource
from twisted.web.proxy import ProxyClient, ProxyClientFactory


class DisconnectAwareProxyClient(ProxyClient):
    """Stop forwarding a response after its recipient disconnects."""

    def handleResponsePart(self, buffer):
        """Forward body bytes only while the downstream request is alive."""
        if not self.factory.downstream_disconnected:
            super().handleResponsePart(buffer)

    def handleResponseEnd(self):
        """Always close upstream, without finishing a disconnected request."""
        if self.factory.downstream_disconnected:
            self._finished = True
            self.transport.loseConnection()
        else:
            super().handleResponseEnd()


class DisconnectAwareProxyFactory(ProxyClientFactory):
    """Observe disconnects before connecting to the upstream server."""

    protocol = DisconnectAwareProxyClient

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.downstream_disconnected = False
        self.father.notifyFinish().addErrback(self._disconnected)

    def _disconnected(self, _failure):
        """Consume the disconnect notification and remember the lifecycle."""
        self.downstream_disconnected = True

    def buildProtocol(self, addr):
        """Attach lifecycle state to the protocol returned by Twisted."""
        protocol = super().buildProtocol(addr)
        protocol.factory = self
        return protocol

    def clientConnectionFailed(self, connector, reason):
        """Send a gateway error only if the downstream request still exists."""
        if not self.downstream_disconnected:
            super().clientConnectionFailed(connector, reason)


class DisconnectAwareProxyResource(EvenniaReverseProxyResource):
    """Keep the disconnect-aware factory on every proxied child path."""

    proxyClientFactoryClass = DisconnectAwareProxyFactory

    def getChild(self, path, _request):
        """Preserve proxy configuration while extending its URL path."""
        return type(self)(
            self.host, self.port, self.path + "/" + quote(path, safe=""), self.reactor
        )
