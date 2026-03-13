"""Tests for game clock API views."""

from datetime import UTC, datetime

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.game_clock.factories import GameClockFactory


class ClockStateViewTests(TestCase):
    """Tests for the GET / clock state endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def test_returns_clock_state(self) -> None:
        """Should return 200 with clock state when a clock exists."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 7, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/clock/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("ic_datetime", data)
        self.assertIn("phase", data)
        self.assertIn("season", data)
        self.assertIn("light_level", data)
        self.assertIn("paused", data)
        self.assertIn("year", data)
        self.assertIn("month", data)
        self.assertIn("day", data)
        self.assertIn("hour", data)
        self.assertIn("minute", data)

    def test_returns_503_when_no_clock(self) -> None:
        """Should return 503 when no clock is configured."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get("/api/clock/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_requires_authentication(self) -> None:
        """Should return 403 when not authenticated."""
        response = self.client.get("/api/clock/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ClockConvertViewTests(TestCase):
    """Tests for the GET /convert/ endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_convert_real_to_ic(self) -> None:
        """Should convert a real date to an IC date."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 6, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(
            anchor_real_time=real_anchor,
            anchor_ic_time=ic_anchor,
            time_ratio=3.0,
        )

        response = self.client.get(
            "/api/clock/convert/",
            {"real_date": "2025-01-01T12:00:00Z"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("ic_date", data)

    def test_convert_ic_to_real(self) -> None:
        """Should convert an IC date to a real date."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 6, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(
            anchor_real_time=real_anchor,
            anchor_ic_time=ic_anchor,
            time_ratio=3.0,
        )

        response = self.client.get(
            "/api/clock/convert/",
            {"ic_date": "0001-06-15T12:00:00Z"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("real_date", data)

    def test_returns_400_with_no_params(self) -> None:
        """Should return 400 when neither ic_date nor real_date is given."""
        GameClockFactory()

        response = self.client.get("/api/clock/convert/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StaffClockAdjustViewTests(TestCase):
    """Tests for staff-only clock management endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff_account = AccountFactory(is_staff=True)
        cls.regular_account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def test_staff_can_adjust_clock(self) -> None:
        """Staff should be able to adjust the clock via POST /adjust/."""
        GameClockFactory()
        self.client.force_authenticate(user=self.staff_account)

        response = self.client.post(
            "/api/clock/adjust/",
            {"ic_datetime": "0001-06-15T12:00:00Z", "reason": "Test adjustment"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_staff_gets_403_on_adjust(self) -> None:
        """Non-staff should get 403 on POST /adjust/."""
        GameClockFactory()
        self.client.force_authenticate(user=self.regular_account)

        response = self.client.post(
            "/api/clock/adjust/",
            {"ic_datetime": "0001-06-15T12:00:00Z", "reason": "Test"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_pause(self) -> None:
        """Staff should be able to pause the clock."""
        GameClockFactory(paused=False)
        self.client.force_authenticate(user=self.staff_account)

        response = self.client.post("/api/clock/pause/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_staff_can_unpause(self) -> None:
        """Staff should be able to unpause the clock."""
        GameClockFactory(paused=True)
        self.client.force_authenticate(user=self.staff_account)

        response = self.client.post("/api/clock/unpause/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_staff_can_change_ratio(self) -> None:
        """Staff should be able to change the time ratio."""
        GameClockFactory()
        self.client.force_authenticate(user=self.staff_account)

        response = self.client.post(
            "/api/clock/ratio/",
            {"ratio": 6.0, "reason": "Speed up for event"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_staff_gets_403_on_pause(self) -> None:
        """Non-staff should get 403 on POST /pause/."""
        GameClockFactory(paused=False)
        self.client.force_authenticate(user=self.regular_account)

        response = self.client.post("/api/clock/pause/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
