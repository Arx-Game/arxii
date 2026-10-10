"""Arx lifecycle guards around Evennia's background maintenance."""

from django.db import close_old_connections
from evennia.server.service import EvenniaServerService


class ArxServerService(EvenniaServerService):
    """Give the minute loop the same connection boundary as game ticks."""

    def server_maintenance(self):
        """Discard stale connections before maintenance performs any query."""
        close_old_connections()
        super().server_maintenance()
