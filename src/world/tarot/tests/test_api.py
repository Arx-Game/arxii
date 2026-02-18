"""Tests for tarot card API."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.tarot.constants import ArcanaType, TarotSuit
from world.tarot.models import TarotCard


class TarotCardAPITest(TestCase):
    """Test tarot card list endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(username="testuser")
        TarotCard.objects.create(
            name="The Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Fatui",
        )
        TarotCard.objects.create(
            name="Three of Swords",
            arcana_type=ArcanaType.MINOR,
            suit=TarotSuit.SWORDS,
            rank=3,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_login(self.account)

    def test_list_tarot_cards(self):
        """Authenticated user can list tarot cards."""
        response = self.client.get("/api/character-creation/tarot-cards/")
        assert response.status_code == 200
        assert len(response.data) == 2

    def test_card_has_surname_fields(self):
        """Response includes computed surname_upright and surname_reversed."""
        response = self.client.get("/api/character-creation/tarot-cards/")
        major = next(c for c in response.data if c["arcana_type"] == "major")
        assert major["surname_upright"] == "Fatui"
        assert major["surname_reversed"] == "N'Fatui"
        minor = next(c for c in response.data if c["arcana_type"] == "minor")
        assert minor["surname_upright"] == "Sword"
        assert minor["surname_reversed"] == "Downsword"

    def test_unauthenticated_returns_403(self):
        """Unauthenticated request is rejected."""
        client = APIClient()
        response = client.get("/api/character-creation/tarot-cards/")
        assert response.status_code == 403
