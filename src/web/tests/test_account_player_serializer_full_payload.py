"""End-to-end payload tests for AccountPlayerSerializer."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import AccountFactory, CharacterFactory
from web.api.payload_helpers import build_account_payload_context
from web.api.serializers import AccountPlayerSerializer
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import ApplicationStatus, RosterApplication, RosterType
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


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
        data = AccountPlayerSerializer(
            self.account,
            context=build_account_payload_context(self.account),
        ).data
        names = [c["name"] for c in data["available_characters"]]
        assert "Bob" in names

    def test_payload_excludes_inactive_character(self) -> None:
        self._add_character(key="Bob", roster=self.active_roster)
        self._add_character(key="Old Hero", roster=self.inactive_roster)
        data = AccountPlayerSerializer(
            self.account,
            context=build_account_payload_context(self.account),
        ).data
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
        data = AccountPlayerSerializer(
            self.account,
            context=build_account_payload_context(self.account),
        ).data
        app_names = [a["character_name"] for a in data["pending_applications"]]
        assert app_names == ["Lyra"]

    def test_payload_no_characters(self) -> None:
        data = AccountPlayerSerializer(
            self.account,
            context=build_account_payload_context(self.account),
        ).data
        assert data["available_characters"] == []
        assert data["pending_applications"] == []

    def test_existing_fields_unchanged(self) -> None:
        """Regression: existing fields must still be present."""
        data = AccountPlayerSerializer(
            self.account,
            context=build_account_payload_context(self.account),
        ).data
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


class AccountPayloadQueryCountTests(TestCase):
    """The payload pipeline should issue a bounded number of queries
    regardless of how many active characters the account has."""

    def setUp(self) -> None:
        self.active_roster = RosterFactory(name=RosterType.ACTIVE)
        self._test_room = None

    def _add_character(self, *, account, key: str) -> None:
        character = CharacterFactory(db_key=key)
        sheet = CharacterSheetFactory(character=character)
        # Add an ESTABLISHED persona to ensure the prefetch is exercised
        Persona.objects.create(
            character_sheet=sheet,
            name=f"{key}-alt",
            persona_type=PersonaType.ESTABLISHED,
        )
        entry = RosterEntryFactory(character_sheet=sheet, roster=self.active_roster)
        RosterTenureFactory(player_data=account.player_data, roster_entry=entry)
        # Place the character in a real Room so last_location actually fires
        # the FK access path (and the query-count test catches a stale
        # select_related chain).
        if self._test_room is None:
            from evennia.utils.create import create_object

            self._test_room = create_object(
                "typeclasses.rooms.Room",
                key=f"{self.__class__.__name__}-room",
                nohome=True,
            )
        character.location = self._test_room
        character.save()

    def test_query_count_does_not_scale_with_character_count(self) -> None:
        # Each measurement uses a separate account to keep state isolated.
        account_one = AccountFactory()
        self._add_character(account=account_one, key="Bob")
        with CaptureQueriesContext(connection) as ctx_one:
            data_one = AccountPlayerSerializer(
                account_one,
                context=build_account_payload_context(account_one),
            ).data
            list(data_one["available_characters"])
        one_count = len(ctx_one.captured_queries)

        account_five = AccountFactory()
        for i in range(5):
            self._add_character(account=account_five, key=f"Char{i}")
        with CaptureQueriesContext(connection) as ctx_five:
            data_five = AccountPlayerSerializer(
                account_five,
                context=build_account_payload_context(account_five),
            ).data
            list(data_five["available_characters"])
        five_count = len(ctx_five.captured_queries)

        # Query count must not scale at all with character count — the
        # prefetch chain is fully bounded.
        assert five_count == one_count, (
            f"Payload query count grew from {one_count} (1 char) to "
            f"{five_count} (5 chars) — N+1 in serializer methods"
        )
