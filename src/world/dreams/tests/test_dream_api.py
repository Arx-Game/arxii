"""Tests for the dreams API view (#3003)."""

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.conditions.models import ConditionTemplate
from world.dreams.services import dreamspace_for, start_dreamwalk
from world.dreams.tests import DreamSleeperTestMixin
from world.relationships.factories import CharacterRelationshipFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.models import SceneRound
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.seeds import (
    ensure_dream_room,
    ensure_foundational_capabilities,
    ensure_sleeping_condition,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class CharacterDreamStateViewTests(DreamSleeperTestMixin, APITestCase):
    """Tests for GET /api/dreams/<character_id>/.

    Gates on SEED_SAMPLE_CONTENT (#2698), same as the rest of the dreams suite.
    """

    def setUp(self) -> None:
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        ensure_dream_room()
        self.template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)

        self.sheet = self._sleeping_sheet("Dreamer")
        self.account = AccountFactory()
        self.tenure = RosterTenureFactory(
            roster_entry__character_sheet=self.sheet,
            player_data__account=self.account,
        )
        self.staff_account = AccountFactory(is_staff=True)
        self.stranger_account = AccountFactory()
        self.url = f"/api/dreams/{self.sheet.pk}/"
        self.client.force_authenticate(user=self.account)

    def test_owner_reads_own_state(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_dreamside"])
        expected_room = dreamspace_for(self.sheet)
        self.assertIsNotNone(response.data["dream_room"])
        self.assertEqual(response.data["dream_room"]["id"], expected_room.pk)
        self.assertEqual(response.data["dream_room"]["key"], expected_room.key)
        self.assertIn("description", response.data["dream_room"])
        self.assertEqual(response.data["co_dreamers"], [])
        self.assertIsNone(response.data["dreamwalk_host"])
        self.assertEqual(response.data["dreamwalk_candidates"], [])
        self.assertFalse(response.data["can_descend"])
        self.assertEqual(response.data["descent_name"], "")
        self.assertFalse(response.data["can_ascend"])
        self.assertFalse(response.data["wake_blocked"])

    def test_staff_reads_any_character(self) -> None:
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_dreamside"])

    def test_stranger_gets_404_not_403(self) -> None:
        self.client.force_authenticate(user=self.stranger_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_character_404(self) -> None:
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get("/api/dreams/999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_wake_blocked_when_active_scene_round(self) -> None:
        dream_room = dreamspace_for(self.sheet)
        SceneRound.objects.create(room_id=dream_room.pk, status="DECLARING")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["wake_blocked"])

    def test_co_dreamers_lists_same_dreamspace_sleeper(self) -> None:
        host = self._sleeping_sheet("Host")
        start_dreamwalk(dreamer=self.sheet, host=host)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        co_dreamer_ids = {entry["id"] for entry in response.data["co_dreamers"]}
        self.assertIn(host.pk, co_dreamer_ids)

    def test_dreamwalk_candidates_lists_bonded_dreamer_and_excludes_unbonded(self) -> None:
        bonded = self._sleeping_sheet("Bonded")
        unbonded = self._sleeping_sheet("Unbonded")
        CharacterRelationshipFactory(
            source=self.sheet,
            target=bonded,
            is_soul_tether=True,
            is_pending=False,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        candidate_ids = {entry["id"] for entry in response.data["dreamwalk_candidates"]}
        self.assertIn(bonded.pk, candidate_ids)
        self.assertNotIn(unbonded.pk, candidate_ids)
