"""The Django admin is the sanctioned place to seed the GameClock singleton."""

from django.test import TestCase
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.game_clock.models import GameClock


class TestGameClockAdminAdd(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("gcroot", "gcroot@example.com", "pw-123456")

    def test_add_form_creates_the_clock_from_an_ic_anchor(self) -> None:
        """A fresh production database has no clock; a superuser seeds it here.

        The anchor's real-time half is stamped at save, so the form asks only
        for the IC datetime (plus ratio/paused, which carry defaults).
        """
        self.client.force_login(self.super)
        before = timezone.now()
        response = self.client.post(
            "/admin/arxii/gameclock/add/",
            {
                "anchor_ic_time_0": "0001-01-01",
                "anchor_ic_time_1": "06:00:00",
                "time_ratio": "3.0",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302, response.content[:500])
        clock = GameClock.get_active()
        self.assertIsNotNone(clock)
        assert clock is not None
        self.assertEqual((clock.anchor_ic_time.year, clock.anchor_ic_time.hour), (1, 6))
        self.assertGreaterEqual(clock.anchor_real_time, before)
