"""The Django admin is the sanctioned place to seed the GameClock singleton."""

from datetime import timedelta

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


class TestGameClockAdminChange(TestCase):
    """The change form shows an existing clock and changes nothing (#5248).

    Saving ``paused`` or ``time_ratio`` there stored the field without moving the
    anchors, so the date jumped: unticking Paused counted all the real time the clock
    had sat paused, at the time ratio.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "gcroot2", "gcroot2@example.com", "pw-123456"
        )

    def test_the_change_form_cannot_unpause_the_clock_or_change_its_speed(self) -> None:
        clock = GameClock.objects.create(
            anchor_real_time=timezone.now() - timedelta(days=7),
            anchor_ic_time=timezone.now().replace(year=1000, month=1, day=1),
            time_ratio=3.0,
            paused=True,
        )
        self.client.force_login(self.super)

        # A form post with Paused unticked (an absent checkbox) and a new ratio.
        response = self.client.post(
            f"/admin/arxii/gameclock/{clock.pk}/change/",
            {"time_ratio": "9.0", "_save": "Save"},
        )

        clock = GameClock.get_active()
        assert clock is not None
        self.assertTrue(clock.paused, "the admin form must not be able to unpause the clock")
        self.assertEqual(clock.time_ratio, 3.0)
        self.assertEqual(response.status_code, 403, "an existing clock is never saved here")

    def test_the_change_form_points_at_the_staff_clock_page(self) -> None:
        clock = GameClock.objects.create(
            anchor_real_time=timezone.now(),
            anchor_ic_time=timezone.now().replace(year=1000, month=1, day=1),
        )
        self.client.force_login(self.super)

        response = self.client.get(f"/admin/arxii/gameclock/{clock.pk}/change/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/staff/clock"')
        self.assertNotContains(response, 'name="_save"')
