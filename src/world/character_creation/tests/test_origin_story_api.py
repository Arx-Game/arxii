"""Tests for the CG origin-template API (#2478)."""

from django.test import TestCase
from rest_framework.test import APIClient

from world.character_creation.models import (
    Beginnings,
    OriginTemplate,
    OriginTemplateSlot,
    StartingArea,
)


class CGOriginTemplateAPITest(TestCase):
    """GET /api/character-creation/origin-templates/?beginning=<id>."""

    def setUp(self) -> None:
        from evennia_extensions.factories import AccountFactory

        self.account = AccountFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

        self.area = StartingArea.objects.create(name="API Test Area")
        self.beginning = Beginnings.objects.create(name="API Beginning", starting_area=self.area)
        self.template = OriginTemplate.objects.create(
            beginning=self.beginning,
            name="Escape",
            frame_narrative="Your story begins with escape.",
        )
        self.slot = OriginTemplateSlot.objects.create(
            template=self.template,
            name="Who helped?",
            prompt="Who aided your flight?",
            example="My sister Mira.",
        )
        self.inactive_template = OriginTemplate.objects.create(
            beginning=self.beginning,
            name="Inactive",
            frame_narrative="...",
            is_active=False,
        )

    def test_list_templates_for_beginning(self) -> None:
        """Active templates for a beginning are returned with nested slots."""
        url = "/api/character-creation/origin-templates/"
        response = self.client.get(url, {"beginning": self.beginning.id})
        assert response.status_code == 200
        data = response.json()
        # Inactive template excluded
        names = [t["name"] for t in data]
        assert "Escape" in names
        assert "Inactive" not in names
        # Slots nested
        template_data = data[0]
        assert len(template_data["slots"]) == 1
        assert template_data["slots"][0]["prompt"] == "Who aided your flight?"
        assert template_data["slots"][0]["example"] == "My sister Mira."

    def test_requires_authentication(self) -> None:
        """Unauthenticated requests are rejected."""
        anon_client = APIClient()
        url = "/api/character-creation/origin-templates/"
        response = anon_client.get(url, {"beginning": self.beginning.id})
        assert response.status_code in (401, 403)


class PostCGOriginSlotAPITest(TestCase):
    """POST set-origin-slot / clear-origin-slot on the sheet (#2478)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.roster.factories import RosterTenureFactory

        cls.tenure = RosterTenureFactory(player_number=1)
        cls.account = cls.tenure.player_data.account
        cls.sheet = cls.tenure.roster_entry.character_sheet

        cls.area = StartingArea.objects.create(name="PostCG Area")
        cls.beginning = Beginnings.objects.create(name="PostCG Beginning", starting_area=cls.area)
        cls.template = OriginTemplate.objects.create(
            beginning=cls.beginning, name="Escape", frame_narrative="..."
        )
        cls.slot = OriginTemplateSlot.objects.create(
            template=cls.template, name="Who helped?", prompt="..."
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _url(self, action: str) -> str:
        return f"/api/character-sheets/{self.sheet.pk}/{action}/"

    def test_set_origin_slot(self) -> None:
        """An owner can set a slot answer via the sheet API."""
        response = self.client.post(
            self._url("set-origin-slot"),
            {"slot_id": self.slot.id, "value": "Mira."},
            format="json",
        )
        assert response.status_code == 200
        from world.character_creation.models import CharacterOriginSlot

        row = CharacterOriginSlot.objects.get(sheet=self.sheet, slot=self.slot)
        assert row.value == "Mira."

    def test_clear_origin_slot(self) -> None:
        """An owner can clear a slot answer."""
        # First set it
        self.client.post(
            self._url("set-origin-slot"),
            {"slot_id": self.slot.id, "value": "Mira."},
            format="json",
        )
        # Then clear it
        response = self.client.post(
            self._url("clear-origin-slot"),
            {"slot_id": self.slot.id},
            format="json",
        )
        assert response.status_code == 200
        from world.character_creation.models import CharacterOriginSlot

        assert not CharacterOriginSlot.objects.filter(sheet=self.sheet, slot=self.slot).exists()

    def test_non_owner_gets_404(self) -> None:
        """A non-owner cannot set a slot answer."""
        from world.roster.factories import RosterTenureFactory

        other_tenure = RosterTenureFactory()
        other_client = APIClient()
        other_client.force_authenticate(user=other_tenure.player_data.account)
        response = other_client.post(
            self._url("set-origin-slot"),
            {"slot_id": self.slot.id, "value": "Mira."},
            format="json",
        )
        assert response.status_code == 404
