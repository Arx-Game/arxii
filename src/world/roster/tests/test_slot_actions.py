"""Tests for the Hall's slot actions (#3996): freeze, thaw, give-up, and the payload."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from web.api.payload_helpers import build_account_payload_context
from web.api.serializers import AccountPlayerSerializer
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.character_sheets.types import ActivityState
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models.choices import CreationProvenance, RosterType
from world.roster.seeds import ensure_rosters


def _held(player_data, provenance):
    entry = RosterEntryFactory(
        character_sheet=CharacterSheetFactory(),
        roster=RosterFactory(roster_type=RosterType.ACTIVE),
        creation_provenance=provenance,
    )
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return entry


class SlotActionViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_rosters()
        cls.account = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.oc = _held(cls.player_data, CreationProvenance.PLAYER)
        cls.roster_char = _held(cls.player_data, CreationProvenance.STAFF)
        cls.stranger = AccountFactory()
        PlayerDataFactory(account=cls.stranger)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_freeze_then_thaw_after_cooldown(self):
        response = self.client.post(f"/api/roster/entries/{self.oc.pk}/freeze/")
        assert response.status_code == 200, response.content
        assert response.data["activity_state"] == ActivityState.FROZEN
        assert response.data["thaw_available_at"] is not None
        assert response.data["creation_provenance"] == CreationProvenance.PLAYER

        early = self.client.post(f"/api/roster/entries/{self.oc.pk}/thaw/")
        assert early.status_code == 400

        # Read the sheet through the manager: setUpTestData hands each test a deep
        # copy, and the view works on the identity-mapped row.
        sheet = CharacterSheet.objects.get(pk=self.oc.character_sheet_id)
        sheet.activity_state_until = timezone.now() - timedelta(days=1)
        sheet.save(update_fields=["activity_state_until"])
        thawed = self.client.post(f"/api/roster/entries/{self.oc.pk}/thaw/")
        assert thawed.status_code == 200, thawed.content
        assert thawed.data["activity_state"] == ActivityState.ACTIVE

    def test_roster_character_cannot_be_frozen(self):
        response = self.client.post(f"/api/roster/entries/{self.roster_char.pk}/freeze/")
        assert response.status_code == 400
        assert "original characters" in response.content.decode()

    def test_give_up_returns_the_character_to_available(self):
        response = self.client.post(f"/api/roster/entries/{self.roster_char.pk}/give-up/")
        assert response.status_code == 200, response.content
        assert response.data["roster_type"] == RosterType.AVAILABLE
        mine = self.client.get("/api/roster/entries/mine/")
        assert [e["id"] for e in mine.data] == [self.oc.pk]

    def test_give_up_refuses_an_original_character(self):
        response = self.client.post(f"/api/roster/entries/{self.oc.pk}/give-up/")
        assert response.status_code == 400
        assert "frozen, not given up" in response.content.decode()

    def test_strangers_entry_is_rejected_uniformly(self):
        self.client.force_authenticate(user=self.stranger)
        for path in ("freeze", "thaw", "give-up"):
            response = self.client.post(f"/api/roster/entries/{self.oc.pk}/{path}/")
            assert response.status_code == 400, path
            assert "one of your characters" in response.content.decode()

    def test_mine_exposes_the_slot_fields(self):
        response = self.client.get("/api/roster/entries/mine/")
        row = next(e for e in response.data if e["id"] == self.roster_char.pk)
        assert row["creation_provenance"] == CreationProvenance.STAFF
        assert row["activity_requirement"] == "HIGH"
        assert row["activity_state"] == ActivityState.ACTIVE
        assert row["thaw_available_at"] is None


class AccountPayloadSlotsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_rosters()
        cls.account = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.account)
        _held(cls.player_data, CreationProvenance.PLAYER)
        cls.staff = AccountFactory(is_staff=True)
        PlayerDataFactory(account=cls.staff)

    def _payload(self, account):
        return AccountPlayerSerializer(account, context=build_account_payload_context(account)).data

    def test_player_payload_carries_the_ledger(self):
        data = self._payload(self.account)
        assert data["character_slots"]["total"] == 4
        assert data["character_slots"]["used"] == 1
        assert data["character_slots"]["holders"][0]["kind"] == "character"

    def test_staff_payload_is_exempt(self):
        data = self._payload(self.staff)
        assert data["character_slots"]["total"] is None
