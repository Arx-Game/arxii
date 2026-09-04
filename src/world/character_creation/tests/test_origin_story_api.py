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
            allows_no_family=True,
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
            allows_no_family=True,
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
            beginning=cls.beginning, name="Escape", frame_narrative="...", allows_no_family=True
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

    def test_player_cannot_change_a_costed_choice_after_approval(self) -> None:
        """A non-staff caller cannot set a pick-list choice via the sheet API (#3617)."""
        from world.character_creation.factories import (
            OriginTemplateSlotChoiceFactory,
            OriginTemplateSlotFactory,
        )

        slot = OriginTemplateSlotFactory(allows_text=False)
        choice = OriginTemplateSlotChoiceFactory(slot=slot)
        response = self.client.post(
            self._url("set-origin-slot"),
            {"slot_id": slot.id, "value": "", "choice_id": choice.id},
            format="json",
        )
        assert response.status_code == 403

    def test_player_can_still_edit_a_write_in(self) -> None:
        """A non-staff caller can still edit a plain write-in slot (#3617)."""
        from world.character_creation.factories import OriginTemplateSlotFactory

        slot = OriginTemplateSlotFactory()
        response = self.client.post(
            self._url("set-origin-slot"),
            {"slot_id": slot.id, "value": "A fuller account."},
            format="json",
        )
        assert response.status_code == 200

    def test_text_edit_preserves_stored_choice(self) -> None:
        """A text-only write on a slot with a stored choice keeps that choice (#3617)."""
        from evennia_extensions.factories import AccountFactory
        from world.character_creation.factories import (
            OriginTemplateSlotChoiceFactory,
            OriginTemplateSlotFactory,
        )
        from world.character_creation.models import CharacterOriginSlot

        slot = OriginTemplateSlotFactory()
        choice = OriginTemplateSlotChoiceFactory(slot=slot)

        staff_account = AccountFactory(is_staff=True)
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff_account)
        set_response = staff_client.post(
            self._url("set-origin-slot"),
            {"slot_id": slot.id, "value": "", "choice_id": choice.id},
            format="json",
        )
        assert set_response.status_code == 200

        response = self.client.post(
            self._url("set-origin-slot"),
            {"slot_id": slot.id, "value": "A fuller account."},
            format="json",
        )
        assert response.status_code == 200
        row = CharacterOriginSlot.objects.get(sheet=self.sheet, slot=slot)
        assert row.choice == choice
        assert row.value == "A fuller account."

    def test_player_cannot_clear_a_choice_backed_slot(self) -> None:
        """A non-staff caller cannot clear a slot holding a costed choice (#3617)."""
        from evennia_extensions.factories import AccountFactory
        from world.character_creation.factories import (
            OriginTemplateSlotChoiceFactory,
            OriginTemplateSlotFactory,
        )
        from world.character_creation.models import CharacterOriginSlot

        slot = OriginTemplateSlotFactory()
        choice = OriginTemplateSlotChoiceFactory(slot=slot)

        staff_account = AccountFactory(is_staff=True)
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff_account)
        staff_client.post(
            self._url("set-origin-slot"),
            {"slot_id": slot.id, "value": "", "choice_id": choice.id},
            format="json",
        )

        response = self.client.post(
            self._url("clear-origin-slot"),
            {"slot_id": slot.id},
            format="json",
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Upbringing choices are set at character creation."
        assert CharacterOriginSlot.objects.filter(sheet=self.sheet, slot=slot).exists()

    def test_player_can_clear_a_text_only_slot(self) -> None:
        """A non-staff caller can still clear a plain write-in slot (#3617)."""
        from world.character_creation.factories import OriginTemplateSlotFactory
        from world.character_creation.models import CharacterOriginSlot

        slot = OriginTemplateSlotFactory()
        self.client.post(
            self._url("set-origin-slot"),
            {"slot_id": slot.id, "value": "A fuller account."},
            format="json",
        )

        response = self.client.post(
            self._url("clear-origin-slot"),
            {"slot_id": slot.id},
            format="json",
        )
        assert response.status_code == 200
        assert not CharacterOriginSlot.objects.filter(sheet=self.sheet, slot=slot).exists()

    def test_staff_can_clear_a_choice_backed_slot(self) -> None:
        """Staff may clear a slot holding a costed choice (#3617)."""
        from evennia_extensions.factories import AccountFactory
        from world.character_creation.factories import (
            OriginTemplateSlotChoiceFactory,
            OriginTemplateSlotFactory,
        )
        from world.character_creation.models import CharacterOriginSlot

        slot = OriginTemplateSlotFactory()
        choice = OriginTemplateSlotChoiceFactory(slot=slot)

        staff_account = AccountFactory(is_staff=True)
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff_account)
        staff_client.post(
            self._url("set-origin-slot"),
            {"slot_id": slot.id, "value": "", "choice_id": choice.id},
            format="json",
        )

        response = staff_client.post(
            self._url("clear-origin-slot"),
            {"slot_id": slot.id},
            format="json",
        )
        assert response.status_code == 200
        assert not CharacterOriginSlot.objects.filter(sheet=self.sheet, slot=slot).exists()
