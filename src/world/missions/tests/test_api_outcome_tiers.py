"""The outcome-tier list a route's tier picker reads (#4558)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.models import EncounterOutcomeMapping
from world.traits.factories import (
    CheckOutcomeFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)

URL = "/api/missions/outcome-tiers/"


class OutcomeTierListTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-tiers", is_staff=True)
        cls.best = CheckOutcomeFactory(name="Tier Best", success_level=2)
        cls.worst = CheckOutcomeFactory(name="Tier Worst", success_level=-2)
        cls.middle = CheckOutcomeFactory(name="Tier Middle", success_level=0)
        cls.mapped_only = CheckOutcomeFactory(name="Tier Mapped", success_level=1)
        cls.unmapped = CheckOutcomeFactory(name="Tier Unmapped", success_level=-1)
        chart = ResultChartFactory()
        for roll, tier in enumerate((cls.best, cls.worst, cls.middle), start=1):
            ResultChartOutcomeFactory(chart=chart, outcome=tier, min_roll=roll, max_roll=roll)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.LOW,
            check_outcome=cls.mapped_only,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_ordered_by_success_level_and_excludes_unmapped(self) -> None:
        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [(t["name"], t["success_level"]) for t in response.data["results"]],
            [("Tier Worst", -2), ("Tier Middle", 0), ("Tier Mapped", 1), ("Tier Best", 2)],
        )
        self.assertEqual(set(response.data["results"][0]), {"id", "name", "success_level"})

    def test_filter_by_name(self) -> None:
        response = self.client.get(URL, {"name": "Tier Best"})
        self.assertEqual([t["id"] for t in response.data["results"]], [self.best.pk])

    def test_read_only(self) -> None:
        response = self.client.post(URL, {"name": "x", "success_level": 0})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_anonymous_refused(self) -> None:
        response = APIClient().get(URL)
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )
