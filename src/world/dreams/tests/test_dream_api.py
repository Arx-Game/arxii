"""Tests for the dreams API view (#3003)."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.services import create_character_with_sheet
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition, get_condition_instance
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

    def test_co_dreamers_lists_dreamwalk_host(self) -> None:
        """Dreamwalking to a host anchors co-dreamer listing on the host (#2290)."""
        host = self._sleeping_sheet("Host")
        start_dreamwalk(dreamer=self.sheet, host=host)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        co_dreamer_ids = {entry["id"] for entry in response.data["co_dreamers"]}
        self.assertIn(host.pk, co_dreamer_ids)

    def test_co_dreamers_lists_same_room_sleeper(self) -> None:
        """Two characters sleeping in the same reflected waking room share a
        dreamspace automatically, no dreamwalk needed (#3003 finding 3) — the
        misnamed predecessor of this test actually started a dreamwalk rather
        than exercising the same-room case; see
        ``test_co_dreamers_lists_dreamwalk_host`` for that coverage.
        """
        roommate_char, roommate_sheet, _ = create_character_with_sheet(
            character_key="Roommate",
            primary_persona_name="Roommate",
        )
        roommate_char.location = self.sheet.character.location
        roommate_char.save()
        apply_condition(target=roommate_char, condition=self.template)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        co_dreamer_ids = {entry["id"] for entry in response.data["co_dreamers"]}
        self.assertIn(roommate_sheet.pk, co_dreamer_ids)

    def test_co_dreamers_excludes_same_room_sleeper_without_reflection(self) -> None:
        """The liminal-placeholder fallback (no real ``DreamReflection``) must
        NOT share co-dreamers by room — that would be unbounded (#3003
        finding 3): every unreflected sleeper in the game resolves to the
        same liminal room.
        """
        unreflected_room = ObjectDBFactory(
            db_key="Unreflected Room", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.sheet.character.location = unreflected_room
        self.sheet.character.save()

        roommate_char, _roommate_sheet, _ = create_character_with_sheet(
            character_key="LiminalRoommate",
            primary_persona_name="LiminalRoommate",
        )
        roommate_char.location = unreflected_room
        roommate_char.save()
        apply_condition(target=roommate_char, condition=self.template)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["co_dreamers"], [])

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

    def test_dreamwalk_candidates_includes_lapsed_suppression(self) -> None:
        """A Sleeping condition whose suppression window has passed still counts (#3003).

        Mirrors get_active_conditions's canonical "active" predicate: suppressed
        AND past suppressed_until means active again, same as perceives_dreamside
        would report via has_condition.
        """
        bonded = self._sleeping_sheet("LapsedSuppression")
        CharacterRelationshipFactory(
            source=self.sheet,
            target=bonded,
            is_soul_tether=True,
            is_pending=False,
        )
        instance = get_condition_instance(bonded.character, self.template, include_suppressed=True)
        instance.is_suppressed = True
        instance.suppressed_until = timezone.now() - timedelta(minutes=1)
        instance.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        candidate_ids = {entry["id"] for entry in response.data["dreamwalk_candidates"]}
        self.assertIn(bonded.pk, candidate_ids)
