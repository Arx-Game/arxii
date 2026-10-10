"""Regression for a stale database connection stopping maintenance."""

from unittest.mock import patch

from django.conf import settings
from django.db import OperationalError
from django.test import SimpleTestCase
from evennia.utils.utils import class_from_module
from twisted.internet.task import Clock, LoopingCall

from server.service import ArxServerService


class ServerMaintenanceTests(SimpleTestCase):
    """The real periodic driver must keep running after a stale connection."""

    def test_configured_service_heals_before_every_maintenance_query(self):
        self.assertIs(class_from_module(settings.EVENNIA_SERVER_SERVICE_CLASS), ArxServerService)
        stale = True
        calls = []

        def heal():
            nonlocal stale
            stale = False
            calls.append("heal")

        def query():
            nonlocal stale
            calls.append("query")
            if stale:
                raise OperationalError
            stale = True  # Simulate another restart between ticks.

        service = object.__new__(ArxServerService)
        clock = Clock()
        loop = LoopingCall(service.server_maintenance)
        loop.clock = clock
        with (
            patch("server.service.close_old_connections", side_effect=heal),
            patch(
                "evennia.server.service.EvenniaServerService.server_maintenance", side_effect=query
            ),
        ):
            completion = loop.start(60, now=True)
            clock.advance(60)
            clock.advance(60)
            self.assertTrue(loop.running)
            self.assertFalse(completion.called)
            loop.stop()
        self.assertEqual(calls, ["heal", "query"] * 3)
