"""Tests for fatigue API views."""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.constants import REST_AP_COST
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool
from world.roster.factories import RosterTenureFactory


class RestViewTests(APITestCase):
    """Tests for POST /api/fatigue/rest/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.sheet.character,
            player_data__account=cls.account,
        )

    def setUp(self) -> None:
        FatiguePool.flush_instance_cache()
        ActionPointPool.flush_instance_cache()
        self.client.force_authenticate(user=self.account)

    def test_rest_succeeds(self) -> None:
        """POST rest sets well_rested and rested_today, spends AP."""
        ActionPointPool.objects.create(
            character=self.sheet.character,
            current=200,
            maximum=200,
        )
        response = self.client.post("/api/fatigue/rest/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pool = get_or_create_fatigue_pool(self.sheet)
        self.assertTrue(pool.well_rested)
        self.assertTrue(pool.rested_today)

    def test_rest_spends_ap(self) -> None:
        """Resting should deduct the configured AP cost."""
        ap_pool = ActionPointPool.objects.create(
            character=self.sheet.character,
            current=200,
            maximum=200,
        )
        self.client.post("/api/fatigue/rest/")
        ap_pool.refresh_from_db()
        self.assertEqual(ap_pool.current, 200 - REST_AP_COST)

    def test_rest_fails_when_already_rested(self) -> None:
        """Cannot rest twice in one day."""
        ActionPointPool.objects.create(
            character=self.sheet.character,
            current=200,
            maximum=200,
        )
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.rested_today = True
        pool.save()

        response = self.client.post("/api/fatigue/rest/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already rested", response.data["detail"].lower())

    def test_rest_fails_with_insufficient_ap(self) -> None:
        """Cannot rest without enough AP."""
        ActionPointPool.objects.create(
            character=self.sheet.character,
            current=REST_AP_COST - 1,
            maximum=200,
        )
        response = self.client.post("/api/fatigue/rest/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("action points", response.data["detail"].lower())

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests should be rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/fatigue/rest/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_no_active_character_returns_404(self) -> None:
        """Account without a roster entry should get 404."""
        other_account = AccountFactory()
        self.client.force_authenticate(user=other_account)
        response = self.client.post("/api/fatigue/rest/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
