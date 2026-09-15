"""The roster payload carries each character's attention counts (#3774)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory, SceneFactory, SceneParticipationFactory
from world.scenes.place_models import InteractionReceiver


class MyRosterEntriesAttentionTests(TestCase):
    url = "/api/roster/entries/mine/"

    @classmethod
    def setUpTestData(cls) -> None:
        # One account with two characters; a whisper waiting for the first.
        cls.account = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.account)

        cls.sheet_one = CharacterSheetFactory()
        cls.persona_one = cls.sheet_one.primary_persona
        cls.entry_one = RosterEntryFactory(character_sheet=cls.sheet_one)
        RosterTenureFactory(player_data=cls.player_data, roster_entry=cls.entry_one)
        cls.character_one_name = cls.sheet_one.character.db_key

        cls.sheet_two = CharacterSheetFactory()
        cls.entry_two = RosterEntryFactory(character_sheet=cls.sheet_two)
        RosterTenureFactory(player_data=cls.player_data, roster_entry=cls.entry_two)
        cls.character_two_name = cls.sheet_two.character.db_key

        cls.outsider = CharacterSheetFactory().primary_persona

        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.account)
        InteractionFactory(scene=cls.scene, persona=cls.persona_one, mode=InteractionMode.POSE)
        whisper = InteractionFactory(
            scene=cls.scene, persona=cls.outsider, mode=InteractionMode.WHISPER
        )
        InteractionReceiver.objects.create(
            interaction=whisper,
            timestamp=whisper.timestamp,
            persona=cls.persona_one,
        )

        # A second, unrelated account with no attention waiting for it.
        cls.other_account = AccountFactory()
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_sheet = CharacterSheetFactory()
        cls.other_entry = RosterEntryFactory(character_sheet=cls.other_sheet)
        RosterTenureFactory(player_data=cls.other_player_data, roster_entry=cls.other_entry)

    def test_fields_reflect_the_service(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)

        response = client.get(self.url)

        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()}
        assert rows[self.character_one_name]["unread_direct"] == 1
        assert rows[self.character_two_name]["unread_direct"] == 0
        assert rows[self.character_two_name]["has_ambient_unread"] is False
        assert rows[self.character_one_name]["attention_as_of_id"] > 0

    def test_another_account_sees_its_own_counts_only(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.other_account)

        response = client.get(self.url)

        assert response.status_code == 200
        for row in response.json():
            assert row["unread_direct"] == 0
            assert row["has_ambient_unread"] is False
