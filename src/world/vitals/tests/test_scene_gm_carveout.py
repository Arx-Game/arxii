"""Tests for the #3434 scene-GM carve-out on CharacterVitalsView._can_view.

Built in ``setUp`` (not ``setUpTestData``): the scenario needs real ObjectDB
rooms/characters with ``db_location`` assigned so ``room.contents`` (which
``Scene.has_character_present`` reads) resolves correctly - factories create
Evennia ObjectDB instances (DbHolder, not deepcopyable), which breaks
``setUpTestData``'s deepcopy. Mirrors ``world.scenes.tests.test_sudden_harm``'s
documented rationale for the same deviation.
"""

from __future__ import annotations

from evennia import create_object
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class SceneGMVitalsCarveoutTests(APITestCase):
    """GET /api/vitals/<character_id>/ - the #3434 scene-GM carve-out."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="VitalsCarveoutRoom", nohome=True)

        self.target_sheet = CharacterSheetFactory()
        self.target_sheet.character.db_location = self.room
        self.target_sheet.character.save(update_fields=["db_location"])

        self.gm_account = AccountFactory()
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)

        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        self.url = f"/api/vitals/{self.target_sheet.pk}/"
        self.client.force_authenticate(user=self.gm_account)

    def test_scene_gm_of_live_scene_containing_target_sees_vitals(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_denied_once_scene_has_ended(self) -> None:
        """Break-the-invariant: same account, scene now finished -> denied."""
        self.scene.is_active = False
        self.scene.save(update_fields=["is_active"])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_denied_once_target_is_elsewhere(self) -> None:
        """Break-the-invariant: same account, target has left the room -> denied."""
        other_room = create_object("typeclasses.rooms.Room", key="ElsewhereRoom", nohome=True)
        self.target_sheet.character.db_location = other_room
        self.target_sheet.character.save(update_fields=["db_location"])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unrelated_gm_denied(self) -> None:
        unrelated_gm = AccountFactory()
        GMProfileFactory(account=unrelated_gm, level=GMLevel.JUNIOR)
        self.client.force_authenticate(user=unrelated_gm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_below_junior_trust_denied(self) -> None:
        """A merely-present STARTING-tier GM does not clear the trust bar."""
        starting_gm = AccountFactory()
        GMProfileFactory(account=starting_gm, level=GMLevel.STARTING)
        SceneParticipationFactory(scene=self.scene, account=starting_gm, is_gm=True)
        self.client.force_authenticate(user=starting_gm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_bypass_preserved(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_own_tenure_unchanged(self) -> None:
        from world.roster.factories import RosterTenureFactory

        owner_account = AccountFactory()
        RosterTenureFactory(
            roster_entry__character_sheet=self.target_sheet,
            player_data__account=owner_account,
        )
        self.client.force_authenticate(user=owner_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_battle_backed_scene_excluded(self) -> None:
        """active_for_room excludes battle-backed scenes - this carve-out never fires there."""
        from world.battles.factories import BattleFactory

        self.scene.delete()
        battle = BattleFactory()
        battle.scene.location = self.room
        battle.scene.save(update_fields=["location"])
        SceneParticipationFactory(scene=battle.scene, account=self.gm_account, is_gm=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
