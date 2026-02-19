"""Tests for tarot card API."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.tarot.constants import ArcanaType, TarotSuit
from world.tarot.models import NamingRitualConfig, TarotCard


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

    def test_card_has_description_reversed_field(self):
        """Response includes description_reversed field."""
        response = self.client.get("/api/character-creation/tarot-cards/")
        assert response.status_code == 200
        for card in response.data:
            assert "description_reversed" in card

    def test_unauthenticated_returns_403(self):
        """Unauthenticated request is rejected."""
        client = APIClient()
        response = client.get("/api/character-creation/tarot-cards/")
        assert response.status_code == 403


class NamingRitualConfigAPITest(TestCase):
    """Test naming ritual config endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(username="testuser2")

    def setUp(self):
        self.client = APIClient()
        self.client.force_login(self.account)

    def test_returns_default_when_no_config(self):
        """Returns default flavor text when no config exists."""
        response = self.client.get("/api/character-creation/naming-ritual-config/")
        assert response.status_code == 200
        assert "Mirrormask" in response.data["flavor_text"]
        assert response.data["codex_entry_id"] is None

    def test_returns_config_when_exists(self):
        """Returns config data when a NamingRitualConfig exists."""
        NamingRitualConfig.objects.create(
            flavor_text="Custom ritual flavor text.",
        )
        response = self.client.get("/api/character-creation/naming-ritual-config/")
        assert response.status_code == 200
        assert response.data["flavor_text"] == "Custom ritual flavor text."
        assert response.data["codex_entry_id"] is None

    def test_unauthenticated_returns_403(self):
        """Unauthenticated request is rejected."""
        client = APIClient()
        response = client.get("/api/character-creation/naming-ritual-config/")
        assert response.status_code == 403
