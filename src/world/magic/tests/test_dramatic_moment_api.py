from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, DramaticMomentTypeFactory
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneParticipationFactory,
)


class DramaticMomentTagApiTest(APITestCase):
    def setUp(self):
        self.url = reverse("magic:dramatic-moment-tag-list")
        self.sheet = CharacterSheetFactory()
        self.resonance_holder = CharacterResonanceFactory(character_sheet=self.sheet)
        self.resonance = self.resonance_holder.resonance
        self.moment_type = DramaticMomentTypeFactory(resonance=self.resonance, per_scene_cap=1)
        self.scene = SceneFactory()
        self.gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)

    def _payload(self):
        return {
            "moment_type": self.moment_type.id,
            "character_sheet": self.sheet.pk,
            "scene": self.scene.id,
        }

    def test_gm_without_is_staff_can_tag(self):
        self.assertFalse(self.gm.is_staff)
        self.client.force_authenticate(self.gm)
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_tagged_by_is_request_account(self):
        self.client.force_authenticate(self.gm)
        resp = self.client.post(self.url, self._payload(), format="json")
        from world.magic.models.dramatic_moment import DramaticMomentTag

        tag = DramaticMomentTag.objects.get(pk=resp.data["id"])
        self.assertEqual(tag.tagged_by_id, self.gm.id)

    def test_non_participant_is_forbidden(self):
        outsider = AccountFactory()
        self.client.force_authenticate(outsider)
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

    def test_cap_exceeded_returns_400(self):
        self.client.force_authenticate(self.gm)
        self.client.post(self.url, self._payload(), format="json")
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_unclaimed_resonance_returns_400(self):
        other_sheet = CharacterSheetFactory()  # no CharacterResonance claimed
        self.client.force_authenticate(self.gm)
        payload = self._payload()
        payload["character_sheet"] = other_sheet.pk
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_owner_can_tag_via_interaction(self):
        owner = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=owner, is_owner=True)
        interaction = InteractionFactory(scene=self.scene)
        # Make the pose author's sheet the claimed-resonance sheet for a clean grant.
        interaction.persona.character_sheet = self.sheet
        interaction.persona.save()
        self.client.force_authenticate(owner)
        resp = self.client.post(
            self.url,
            {"moment_type": self.moment_type.id, "interaction": interaction.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
