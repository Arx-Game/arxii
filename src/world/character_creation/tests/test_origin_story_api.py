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
