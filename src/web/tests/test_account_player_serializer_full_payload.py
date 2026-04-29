"""End-to-end payload tests for AccountPlayerSerializer."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from web.api.serializers import AccountPlayerSerializer
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import ApplicationStatus, RosterApplication, RosterType


class AccountPlayerSerializerFullPayloadTests(TestCase):
    """The /api/user/ payload should include character + application data."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.active_roster = RosterFactory(name=RosterType.ACTIVE)
        self.inactive_roster = RosterFactory(name=RosterType.INACTIVE)

    def _add_character(self, *, key: str, roster) -> None:
        character = CharacterFactory(db_key=key)
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
        RosterTenureFactory(player_data=self.account.player_data, roster_entry=entry)

    def test_payload_includes_active_character(self) -> None:
        self._add_character(key="Bob", roster=self.active_roster)
        data = AccountPlayerSerializer(self.account).data
        names = [c["name"] for c in data["available_characters"]]
        assert "Bob" in names

    def test_payload_excludes_inactive_character(self) -> None:
        self._add_character(key="Bob", roster=self.active_roster)
        self._add_character(key="Old Hero", roster=self.inactive_roster)
        data = AccountPlayerSerializer(self.account).data
        names = [c["name"] for c in data["available_characters"]]
        assert "Old Hero" not in names
        assert "Bob" in names

    def test_payload_pending_applications(self) -> None:
        target = CharacterFactory(db_key="Lyra")
        RosterApplication.objects.create(
            player_data=self.account.player_data,
            character=target,
            application_text="please",
            status=ApplicationStatus.PENDING,
        )
        # Approved application should NOT appear
        approved_target = CharacterFactory(db_key="Maeve")
        RosterApplication.objects.create(
            player_data=self.account.player_data,
            character=approved_target,
            application_text="please",
            status=ApplicationStatus.APPROVED,
        )
        data = AccountPlayerSerializer(self.account).data
        app_names = [a["character_name"] for a in data["pending_applications"]]
        assert app_names == ["Lyra"]

    def test_payload_no_characters(self) -> None:
        data = AccountPlayerSerializer(self.account).data
        assert data["available_characters"] == []
        assert data["pending_applications"] == []

    def test_existing_fields_unchanged(self) -> None:
        """Regression: existing fields must still be present."""
        data = AccountPlayerSerializer(self.account).data
        for field in [
            "id",
            "username",
            "display_name",
            "last_login",
            "email",
            "email_verified",
            "can_create_characters",
            "is_staff",
            "avatar_url",
        ]:
            assert field in data, f"missing existing field: {field}"
