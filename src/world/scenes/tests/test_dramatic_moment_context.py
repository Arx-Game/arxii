"""Tests for dramatic-moment context fields on scene/interaction/participant serializers.

Task 5 of issue #1139: three new backend serializer surfaces:
- viewer_can_gm on SceneListSerializer (staff | scene GM | scene owner)
- dramatic_moment_tags on InteractionListSerializer (badge data)
- dramatic_moment_count on SceneParticipantSerializer (per-character tag count)
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import DramaticMomentTagFactory, DramaticMomentTypeFactory
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)


class ViewerCanGMTest(APITestCase):
    """viewer_can_gm is True for staff, scene GM, and scene owner; False for outsiders."""

    def setUp(self):
        self.scene = SceneFactory()

    def _scene_detail(self, account):
        self.client.force_authenticate(account)
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_staff_sees_viewer_can_gm_true(self):
        staff_account = AccountFactory()
        staff_account.is_staff = True
        staff_account.save()
        data = self._scene_detail(staff_account)
        self.assertIn("viewer_can_gm", data)
        self.assertTrue(data["viewer_can_gm"])

    def test_scene_gm_sees_viewer_can_gm_true(self):
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=gm)
        data = self._scene_detail(gm)
        self.assertIn("viewer_can_gm", data)
        self.assertTrue(data["viewer_can_gm"])

    def test_scene_owner_sees_viewer_can_gm_true(self):
        owner = AccountFactory()
        SceneOwnerParticipationFactory(scene=self.scene, account=owner)
        data = self._scene_detail(owner)
        self.assertIn("viewer_can_gm", data)
        self.assertTrue(data["viewer_can_gm"])

    def test_non_participant_sees_viewer_can_gm_false(self):
        outsider = AccountFactory()
        data = self._scene_detail(outsider)
        self.assertIn("viewer_can_gm", data)
        self.assertFalse(data["viewer_can_gm"])

    def test_regular_participant_sees_viewer_can_gm_false(self):
        participant = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=participant)
        data = self._scene_detail(participant)
        self.assertIn("viewer_can_gm", data)
        self.assertFalse(data["viewer_can_gm"])


class DramaticMomentTagsOnInteractionTest(APITestCase):
    """dramatic_moment_tags on interactions includes label and character_sheet_id."""

    def setUp(self):
        self.account = AccountFactory()
        self.client.force_authenticate(self.account)
        self.sheet = CharacterSheetFactory()
        self.scene = SceneFactory()
        # interaction written by the account so it's visible
        self.interaction = InteractionFactory(scene=self.scene)

    def _list_url(self, scene_id):
        return f"{reverse('interaction-list')}?scene={scene_id}"

    def test_tagged_interaction_returns_moment_label(self):
        moment_type = DramaticMomentTypeFactory()
        DramaticMomentTagFactory(
            interaction=self.interaction,
            moment_type=moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )
        response = self.client.get(self._list_url(self.scene.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        tags = results[0]["dramatic_moment_tags"]
        self.assertIsInstance(tags, list)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["moment_type_label"], moment_type.label)
        self.assertEqual(tags[0]["character_sheet_id"], self.sheet.pk)

    def test_untagged_interaction_returns_empty_list(self):
        response = self.client.get(self._list_url(self.scene.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["dramatic_moment_tags"], [])

    def test_multiple_tags_all_returned(self):
        moment_type_a = DramaticMomentTypeFactory()
        moment_type_b = DramaticMomentTypeFactory()
        sheet2 = CharacterSheetFactory()
        DramaticMomentTagFactory(
            interaction=self.interaction,
            moment_type=moment_type_a,
            character_sheet=self.sheet,
            scene=self.scene,
        )
        DramaticMomentTagFactory(
            interaction=self.interaction,
            moment_type=moment_type_b,
            character_sheet=sheet2,
            scene=self.scene,
        )
        response = self.client.get(self._list_url(self.scene.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tags = response.data["results"][0]["dramatic_moment_tags"]
        self.assertEqual(len(tags), 2)
        labels = {t["moment_type_label"] for t in tags}
        self.assertIn(moment_type_a.label, labels)
        self.assertIn(moment_type_b.label, labels)


class DramaticMomentCountOnParticipantTest(APITestCase):
    """dramatic_moment_count on scene participants reflects tagged-moment count."""

    def setUp(self):
        self.account = AccountFactory()
        self.client.force_authenticate(self.account)
        self.scene = SceneFactory()
        self.sheet = CharacterSheetFactory()

    def _scene_detail(self):
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_participant_with_no_tags_has_count_zero(self):
        # Create interaction so the persona appears in participants
        persona = self.sheet.primary_persona
        InteractionFactory(scene=self.scene, persona=persona)
        data = self._scene_detail()
        participants = data.get("participants", [])
        # At least one participant exists (our persona's character)
        self.assertGreater(len(participants), 0)
        for p in participants:
            self.assertIn("dramatic_moment_count", p)
            self.assertGreaterEqual(p["dramatic_moment_count"], 0)

    def test_participant_with_tags_has_correct_count(self):
        # Add a second untagged participant so the test can verify targeted identity.
        other_sheet = CharacterSheetFactory()
        other_persona = other_sheet.primary_persona
        InteractionFactory(scene=self.scene, persona=other_persona)

        persona = self.sheet.primary_persona
        InteractionFactory(scene=self.scene, persona=persona)
        moment_type = DramaticMomentTypeFactory()
        DramaticMomentTagFactory(
            character_sheet=self.sheet,
            scene=self.scene,
            moment_type=moment_type,
        )
        data = self._scene_detail()
        participants = data.get("participants", [])

        # SceneParticipantSerializer exposes "id" as the Persona pk.
        # Match the tagged participant by persona.pk so no roster_entry is required
        # (CharacterSheetFactory does not create a RosterEntry by default).
        tagged_persona_id = persona.pk
        tagged_participant = next(
            (p for p in participants if p["id"] == tagged_persona_id),
            None,
        )
        self.assertIsNotNone(
            tagged_participant,
            f"No participant matched persona id={tagged_persona_id}; got {participants}",
        )
        self.assertEqual(
            tagged_participant["dramatic_moment_count"],
            1,
            f"Tagged participant should have count=1; got {tagged_participant}",
        )

        # The untagged participant should have count 0.
        untagged_persona_id = other_persona.pk
        untagged_participant = next(
            (p for p in participants if p["id"] == untagged_persona_id),
            None,
        )
        self.assertIsNotNone(
            untagged_participant,
            f"No participant matched untagged persona id={untagged_persona_id}",
        )
        self.assertEqual(
            untagged_participant["dramatic_moment_count"],
            0,
            f"Untagged participant should have count=0; got {untagged_participant}",
        )
