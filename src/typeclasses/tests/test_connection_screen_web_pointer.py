"""#2122 — the telnet connection screen signposts the web app.

The connection screen is the very first thing a telnet-only player sees, before
any account exists. It has no dispatch seam — just a formatted module-level
string — so this is a direct string-content assertion (per the spec's Testing
section).
"""

from django.conf import settings
from django.test import TestCase


class ConnectionScreenWebPointerTests(TestCase):
    def test_connection_screen_mentions_frontend_url(self):
        from server.conf.connection_screens import CONNECTION_SCREEN

        self.assertIn(settings.FRONTEND_URL, CONNECTION_SCREEN)
