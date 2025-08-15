"""Tests for RosterTenureViewSet search."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from world.roster.factories import (
    CharacterFactory,
    PlayerDataFactory,
    RosterTenureFactory,
)


class RosterTenureViewSetTestCase(TestCase):
    """Test tenure search endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.player = PlayerDataFactory()
        self.client.force_authenticate(self.player.account)
        char = CharacterFactory(db_key="Ariel")
        self.tenure1 = RosterTenureFactory(
            roster_entry__character=char,
            start_date=timezone.now() - timedelta(days=2),
        )
        self.tenure2 = RosterTenureFactory(
            roster_entry=self.tenure1.roster_entry,
            player_number=2,
            start_date=timezone.now() - timedelta(days=1),
        )

    def test_search_orders_most_recent_first(self):
        url = reverse("roster:tenures-list") + "?search=Ariel"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [self.tenure2.id, self.tenure1.id])
