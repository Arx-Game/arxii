"""GM story-NPC on-ramp action tests (#3426) — MintStoryNPCAction gates + journey."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from evennia import create_object
from rest_framework import status
from rest_framework.test import APITestCase

from actions.definitions.gm_npcs import MintStoryNPCAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory


def _make_room(key: str = "The GM's Study") -> object:
    return create_object("typeclasses.rooms.Room", key=key, nohome=True)


class MintStoryNPCActionTestBase(TestCase):
    """Shared actor helpers, mirroring test_gm_catalog_actions.py's pattern."""

    def _nonstaff_character(self, *, db_key: str = "npc-onlooker") -> object:
        account = AccountFactory(is_staff=False, username=f"{db_key}-acct")
        character = CharacterFactory(db_key=db_key, location=_make_room())
        character.db_account = account
        return character

    def _gm_character(self, level: str, *, db_key: str = "npc-gm") -> object:
        character = CharacterFactory(db_key=db_key, location=_make_room())
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        GMProfileFactory(account=tenure.player_data.account, level=level)
        character.db_account = tenure.player_data.account
        return character


class MintStoryNPCActionPermissionTests(MintStoryNPCActionTestBase):
    def test_non_gm_is_refused(self) -> None:
        actor = self._nonstaff_character()
        result = MintStoryNPCAction().run(actor=actor, name="Should Not Exist")
        assert result.success is False

    def test_starting_gm_refused(self) -> None:
        seed_default_gm_level_caps()
        actor = self._gm_character(GMLevel.STARTING)
        result = MintStoryNPCAction().run(actor=actor, name="Too Junior")
        assert result.success is False

    def test_junior_gm_can_mint(self) -> None:
        seed_default_gm_level_caps()
        actor = self._gm_character(GMLevel.JUNIOR)
        result = MintStoryNPCAction().run(
            actor=actor, name="Master Aldous", description="A grim watchman."
        )
        assert result.success is True
        assert "Master Aldous" in (result.message or "")

    def test_missing_name_refused(self) -> None:
        seed_default_gm_level_caps()
        actor = self._gm_character(GMLevel.JUNIOR)
        result = MintStoryNPCAction().run(actor=actor, name="   ")
        assert result.success is False

    def test_capped_out_gm_refused(self) -> None:
        seed_default_gm_level_caps()  # JUNIOR's seeded cap is 2.
        actor = self._gm_character(GMLevel.JUNIOR)
        assert MintStoryNPCAction().run(actor=actor, name="First NPC").success is True
        assert MintStoryNPCAction().run(actor=actor, name="Second NPC").success is True

        result = MintStoryNPCAction().run(actor=actor, name="Third NPC")
        assert result.success is False
        assert "story NPC" in (result.message or "")


class MintStoryNPCJourneyTests(APITestCase):
    """The real user goal (#3426): mint, then post a scene action AS the NPC persona."""

    def test_gm_mints_npc_and_posts_a_scene_action_as_it(self) -> None:
        from world.scenes.models import Persona

        seed_default_gm_level_caps()
        room = _make_room()
        gm_character = CharacterFactory(db_key="journey-gm", location=room)
        gm_identity = CharacterSheetFactory(character=gm_character)
        gm_persona = gm_identity.primary_persona
        gm_entry = RosterEntryFactory(character_sheet=gm_identity)
        gm_tenure = RosterTenureFactory(roster_entry=gm_entry, end_date=None)
        gm_account = gm_tenure.player_data.account
        GMProfileFactory(account=gm_account, level=GMLevel.JUNIOR)
        gm_character.db_account = gm_account

        result = MintStoryNPCAction().run(
            actor=gm_character, name="Master Aldous", description="A grim watchman."
        )
        assert result.success is True, result.message

        # The persona picker / telnet @ic keys on RosterTenure -- the mint must have
        # bound a tenure to gm_account for this to resolve at all.
        npc_persona = Persona.objects.get(character_sheet__character__db_key="Master Aldous")

        scene = SceneFactory()
        self.client.force_authenticate(user=gm_account)
        url = reverse("sceneactionrequest-list")
        response = self.client.post(
            url,
            {
                "scene": scene.pk,
                "initiator_persona": npc_persona.pk,
                "target_persona": gm_persona.pk,
                "action_key": "intimidate",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.content
        assert response.data["action_key"] == "intimidate"
