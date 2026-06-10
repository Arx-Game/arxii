"""Tests for the vitals API view."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionInstanceFactory,
)
from world.fatigue.models import FatiguePool
from world.fatigue.tests import setup_stat
from world.roster.factories import RosterTenureFactory
from world.traits.models import TraitCategory
from world.vitals.constants import (
    DERIVED_STATUS_ALIVE,
    DERIVED_STATUS_DYING,
)
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import CharacterVitals


class CharacterVitalsViewTests(APITestCase):
    """Tests for GET /api/vitals/<character_id>/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.sheet.character,
            player_data__account=cls.account,
        )
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet, health=75, max_health=100, base_max_health=100
        )
        setup_stat(cls.sheet.character, "stamina", 30, TraitCategory.PHYSICAL)
        setup_stat(cls.sheet.character, "composure", 20, TraitCategory.SOCIAL)
        setup_stat(cls.sheet.character, "stability", 20, TraitCategory.MENTAL)
        setup_stat(cls.sheet.character, "willpower", 20, TraitCategory.META)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.stranger_account = AccountFactory()
        cls.url = f"/api/vitals/{cls.sheet.pk}/"

    def setUp(self) -> None:
        CharacterVitals.flush_instance_cache()
        FatiguePool.flush_instance_cache()
        self.client.force_authenticate(user=self.account)

    def test_owner_gets_full_payload(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["health"], 75)
        self.assertEqual(response.data["max_health"], 100)
        self.assertAlmostEqual(response.data["health_percentage"], 0.75)
        self.assertIsInstance(response.data["wound_description"], str)
        self.assertEqual(response.data["status"], DERIVED_STATUS_ALIVE)
        for cat in ("physical", "social", "mental"):
            self.assertIn("current", response.data["fatigue"][cat])
            self.assertIn("capacity", response.data["fatigue"][cat])
            self.assertIn("percentage", response.data["fatigue"][cat])
            self.assertIn("zone", response.data["fatigue"][cat])
        self.assertIn("well_rested", response.data["fatigue"])
        self.assertIn("rested_today", response.data["fatigue"])

    def test_staff_sees_other_character(self) -> None:
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["health"], 75)

    def test_stranger_gets_404(self) -> None:
        self.client.force_authenticate(user=self.stranger_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_unknown_character_404(self) -> None:
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get("/api/vitals/999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_vitals_row_returns_defensive_defaults(self) -> None:
        bare_sheet = CharacterSheetFactory()
        RosterTenureFactory(
            roster_entry__character_sheet__character=bare_sheet.character,
            player_data=self.tenure.player_data,
        )
        response = self.client.get(f"/api/vitals/{bare_sheet.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["health"], 0)
        self.assertEqual(response.data["max_health"], 0)
        self.assertEqual(response.data["health_percentage"], 0.0)
        self.assertEqual(response.data["wound_description"], "")
        self.assertEqual(response.data["status"], DERIVED_STATUS_ALIVE)

    def test_read_does_not_create_fatigue_row(self) -> None:
        self.client.get(self.url)
        self.assertFalse(FatiguePool.objects.filter(character_sheet=self.sheet).exists())

    def test_bleeding_out_reports_dying(self) -> None:
        template = BleedingOutConditionFactory()
        ConditionInstanceFactory(target=self.sheet.character, condition=template)
        response = self.client.get(self.url)
        self.assertEqual(response.data["status"], DERIVED_STATUS_DYING)

    def test_repeat_request_rides_identity_map(self) -> None:
        """Second call must not re-query sheet/vitals/fatigue rows."""
        from world.fatigue.services import get_or_create_fatigue_pool

        get_or_create_fatigue_pool(self.sheet)  # provision so the accessor is a hit, not a miss
        CharacterSheet.flush_instance_cache()
        CharacterVitals.flush_instance_cache()
        FatiguePool.flush_instance_cache()
        self.client.get(self.url)  # warm the identity map
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        joined = " ".join(q["sql"].lower() for q in ctx.captured_queries)
        self.assertNotIn("vitals_charactervitals", joined)
        self.assertNotIn("fatigue_fatiguepool", joined)
        self.assertNotIn("character_sheets_charactersheet", joined)
