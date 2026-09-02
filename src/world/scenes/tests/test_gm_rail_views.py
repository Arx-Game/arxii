"""Tests for GET /api/scenes/{id}/gm-rail/ (#3434).

Built as instance methods (not ``setUpTestData``): the scenario needs real
ObjectDB rooms/characters, which ``ObjectDBFactory``/``CharacterFactory``
create via Evennia's ``create_object`` - not deepcopyable, so per-test
creation is required (mirrors ``SceneViewSetTestCase`` in ``test_views.py``).
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.clues.factories import RoomClueFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.societies.constants import RenownRisk
from world.stories.constants import StakeResolutionColumn, StakeSeverity
from world.stories.factories import (
    BeatFactory,
    StakeFactory,
    StakeOutcomeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.models import StakeContractActivation


class GMStoryRailViewTests(APITestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="RailRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        self.gm_account = AccountFactory()
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        self.story = StoryFactory()
        self.beat = BeatFactory(episode__chapter__story=self.story)
        self.scene.running_beat = self.beat
        self.scene.save(update_fields=["running_beat"])

        self.url = reverse("scene-gm-rail", kwargs={"pk": self.scene.pk})
        self.client.force_authenticate(user=self.gm_account)

    def test_qualifying_gm_sees_beat_summary(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        beat = response.data["beat"]
        self.assertEqual(beat["id"], self.beat.id)
        self.assertEqual(beat["kind"], self.beat.kind)
        self.assertEqual(beat["risk"], self.beat.risk)
        self.assertEqual(beat["outcome"], self.beat.outcome)

    def test_co_gm_with_no_story_standing_gets_empty_protected_subjects(self) -> None:
        """The leak test (#3434 spec) - must not skip this."""
        StoryProtectedSubjectFactory(story=self.story, is_active=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["protected_subjects"], [])
        self.assertIsNone(response.data["beat"]["internal_description"])
        self.assertIsNone(response.data["beat"]["opponent_lines"])
        self.assertIsNone(response.data["beat"]["staged_templates"])

    def test_story_owner_gm_sees_protected_subjects_and_internal_text(self) -> None:
        self.story.owners.add(self.gm_account)
        protected = StoryProtectedSubjectFactory(story=self.story, is_active=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subject_ids = [row["id"] for row in response.data["protected_subjects"]]
        self.assertIn(protected.id, subject_ids)
        self.assertEqual(
            response.data["beat"]["internal_description"], self.beat.internal_description
        )
        self.assertIsNotNone(response.data["beat"]["opponent_lines"])
        self.assertIsNotNone(response.data["beat"]["staged_templates"])

    def test_story_owner_gm_sees_stakes_with_outcome_and_activation(self) -> None:
        """A story-standing GM sees the contract's stakes (with the fired
        outcome after resolution) and the locked activation (#3561)."""
        self.story.owners.add(self.gm_account)
        stake = StakeFactory(
            beat=self.beat,
            severity=StakeSeverity.DIRE,
            player_summary="A dueling scar, worn for all to see.",
        )
        resolution = StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="",
            narrative_summary="It goes badly.",
        )
        StakeOutcomeFactory(stake=stake, column=StakeResolutionColumn.LOSS, resolution=resolution)
        activation = StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=4,
            declared_target_level=4,
            declared_risk=RenownRisk.HIGH,
            effective_risk=RenownRisk.HIGH,
            is_ready=True,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stakes = response.data["stakes"]
        self.assertEqual(len(stakes), 1)
        self.assertEqual(stakes[0]["id"], stake.pk)
        self.assertEqual(stakes[0]["player_summary"], stake.player_summary)
        self.assertEqual(stakes[0]["severity"], stake.severity)
        self.assertEqual(stakes[0]["subject_kind"], stake.subject_kind)
        self.assertEqual(stakes[0]["outcome"]["column"], StakeResolutionColumn.LOSS)
        self.assertEqual(stakes[0]["outcome"]["outcome_key"], "")
        self.assertEqual(stakes[0]["outcome"]["resolution_summary"], "It goes badly.")
        self.assertEqual(response.data["activation"]["effective_risk"], RenownRisk.HIGH)
        self.assertTrue(response.data["activation"]["is_ready"])
        self.assertIsNotNone(response.data["activation"]["locked_at"])
        self.assertEqual(
            StakeContractActivation.objects.get(pk=activation.pk).effective_risk, RenownRisk.HIGH
        )

    def test_co_gm_with_no_story_standing_gets_empty_stakes_and_no_activation(self) -> None:
        """The leak test's #3561 sibling - stakes and activation gate exactly
        like protected_subjects does."""
        StakeFactory(beat=self.beat, severity=StakeSeverity.DIRE)
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=4,
            declared_target_level=4,
            declared_risk=RenownRisk.HIGH,
            effective_risk=RenownRisk.HIGH,
            is_ready=True,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["stakes"], [])
        self.assertIsNone(response.data["activation"])

    def test_clue_placements_absent_for_non_staff(self) -> None:
        RoomClueFactory(room_profile__objectdb=self.room)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["clue_placements"], [])

    def test_clue_placements_present_for_staff(self) -> None:
        room_clue = RoomClueFactory(room_profile__objectdb=self.room)
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        clue_ids = [row["id"] for row in response.data["clue_placements"]]
        self.assertIn(room_clue.id, clue_ids)

    def test_participants_reflect_room_contents(self) -> None:
        char = CharacterFactory(location=self.room)
        sheet = CharacterSheetFactory(character=char)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        participant_ids = [row["character_sheet_id"] for row in response.data["participants"]]
        self.assertIn(sheet.pk, participant_ids)

    def test_unrelated_gm_denied(self) -> None:
        unrelated_gm = AccountFactory()
        GMProfileFactory(account=unrelated_gm, level=GMLevel.JUNIOR)
        self.client.force_authenticate(user=unrelated_gm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_below_junior_trust_denied(self) -> None:
        starting_gm = AccountFactory()
        GMProfileFactory(account=starting_gm, level=GMLevel.STARTING)
        SceneParticipationFactory(scene=self.scene, account=starting_gm, is_gm=True)
        self.client.force_authenticate(user=starting_gm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_scene_owner_who_is_not_gm_denied(self) -> None:
        """IsSceneGMOrOwnerOrStaff would pass an owner; this endpoint must not."""
        owner_account = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=owner_account, is_owner=True)
        self.client.force_authenticate(user=owner_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_bypass(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
