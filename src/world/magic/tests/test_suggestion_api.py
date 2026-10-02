"""Tests for the dramatic-moment suggestion confirm/dismiss web surface (#2183).

Task 6 of the technique-entrance feature: the REGISTRY actions
(``confirm_dramatic_moment_suggestion`` / ``dismiss_dramatic_moment_suggestion``),
``DramaticMomentSuggestionViewSet`` (list/confirm/dismiss), and
``InteractionSerializer.dramatic_moment_suggestions`` (GM-gated payload field).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptStatus
from world.gm.factories import GMPromptFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
)
from world.magic.models import ResonanceGrant
from world.magic.models.dramatic_moment import DramaticMomentTag
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)


class DramaticMomentSuggestionListTest(APITestCase):
    """GET .../dramatic-moment-suggestions/?scene=<id> — GM-gated PENDING list."""

    def setUp(self):
        self.list_url = reverse("magic:dramatic-moment-suggestion-list")
        self.sheet = CharacterSheetFactory()
        self.resonance_holder = CharacterResonanceFactory(character_sheet=self.sheet)
        self.moment_type = DramaticMomentTypeFactory(resonance=self.resonance_holder.resonance)
        self.scene = SceneFactory()
        self.gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        self.suggestion = GMPromptFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )

    def test_gm_lists_pending_suggestions(self):
        self.client.force_authenticate(self.gm)
        resp = self.client.get(self.list_url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        results = resp.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.suggestion.pk)
        self.assertEqual(results[0]["moment_type_label"], self.moment_type.label)

    def test_resolved_suggestion_is_excluded(self):
        GMPromptFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
            status=GMPromptStatus.DISMISSED,
        )
        self.client.force_authenticate(self.gm)
        resp = self.client.get(self.list_url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data["results"]), 1)

    def test_owner_can_list(self):
        owner = AccountFactory()
        SceneOwnerParticipationFactory(scene=self.scene, account=owner)
        self.client.force_authenticate(owner)
        resp = self.client.get(self.list_url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data["results"]), 1)

    def test_non_gm_participant_is_forbidden(self):
        participant = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=participant)
        self.client.force_authenticate(participant)
        resp = self.client.get(self.list_url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

    def test_missing_scene_param_is_400(self):
        self.client.force_authenticate(self.gm)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)


class DramaticMomentSuggestionConfirmDismissTest(APITestCase):
    """POST .../{id}/confirm/ and .../{id}/dismiss/."""

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance_holder = CharacterResonanceFactory(character_sheet=self.sheet)
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance_holder.resonance, per_scene_cap=1
        )
        self.scene = SceneFactory()
        self.gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        self.suggestion = GMPromptFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )

    def _url(self, action: str, suggestion_id: int | None = None) -> str:
        return reverse(
            f"magic:dramatic-moment-suggestion-{action}",
            kwargs={"pk": suggestion_id or self.suggestion.pk},
        )

    def test_gm_confirms_mints_tag_and_grants_resonance(self):
        self.client.force_authenticate(self.gm)
        resp = self.client.post(self._url("confirm"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["status"], GMPromptStatus.CONFIRMED)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.CONFIRMED)
        self.assertIsNotNone(self.suggestion.confirmed_tag)
        self.assertTrue(
            DramaticMomentTag.objects.filter(pk=self.suggestion.confirmed_tag_id).exists()
        )
        self.assertTrue(
            ResonanceGrant.objects.filter(character_sheet=self.sheet, amount=15).exists()
        )

    def test_gm_dismisses_no_tag(self):
        self.client.force_authenticate(self.gm)
        resp = self.client.post(self._url("dismiss"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.DISMISSED)
        self.assertIsNone(self.suggestion.confirmed_tag)

    def test_non_gm_participant_confirm_is_forbidden(self):
        participant = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=participant)
        self.client.force_authenticate(participant)
        resp = self.client.post(self._url("confirm"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.PENDING)

    def test_confirm_after_cap_returns_400_with_user_message(self):
        DramaticMomentTagFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )
        self.client.force_authenticate(self.gm)
        resp = self.client.post(self._url("confirm"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("detail", resp.data)
        self.assertTrue(resp.data["detail"])
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.PENDING)

    def test_double_confirm_returns_400(self):
        self.client.force_authenticate(self.gm)
        first = self.client.post(self._url("confirm"))
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        second = self.client.post(self._url("confirm"))
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST, second.data)
        self.assertIn("detail", second.data)
        self.assertTrue(second.data["detail"])


class DramaticMomentSuggestionsOnInteractionTest(APITestCase):
    """InteractionSerializer.dramatic_moment_suggestions is GM-gated (#2183)."""

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance_holder = CharacterResonanceFactory(character_sheet=self.sheet)
        self.moment_type = DramaticMomentTypeFactory(resonance=self.resonance_holder.resonance)
        self.scene = SceneFactory()
        self.interaction = InteractionFactory(scene=self.scene)
        self.suggestion = GMPromptFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
            interaction=self.interaction,
        )

    def _list_url(self):
        return f"{reverse('interaction-list')}?scene={self.scene.pk}"

    def test_gm_sees_pending_suggestion(self):
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=gm)
        self.client.force_authenticate(gm)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        results = resp.data["results"]
        self.assertEqual(len(results), 1)
        suggestions = results[0]["dramatic_moment_suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["id"], self.suggestion.pk)
        self.assertEqual(suggestions[0]["moment_type_label"], self.moment_type.label)

    def test_plain_participant_sees_empty_list(self):
        participant = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=participant)
        self.client.force_authenticate(participant)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        results = resp.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["dramatic_moment_suggestions"], [])

    def test_resolved_suggestion_absent_even_for_gm(self):
        self.suggestion.status = GMPromptStatus.CONFIRMED
        self.suggestion.save()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=gm)
        self.client.force_authenticate(gm)
        resp = self.client.get(self._list_url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["results"][0]["dramatic_moment_suggestions"], [])


class DramaticMomentSuggestionActionsRegistryTest(APITestCase):
    """Registry keys exist and are wired.

    The exact-match assertion for the whole registry lives in
    ``actions.tests.test_base``.
    """

    def test_confirm_and_dismiss_keys_registered(self):
        from actions.registry import get_action

        self.assertIsNotNone(get_action("confirm_dramatic_moment_suggestion"))
        self.assertIsNotNone(get_action("dismiss_dramatic_moment_suggestion"))


class DramaticMomentSuggestionNarrationLeakTest(APITestCase):
    """A narration-kind GMPrompt (#4101) must never surface through this
    dramatic_moment-only inbox -- list, confirm, and dismiss all stay blind to it,
    even for the scene's own owner/GM, since it is addressed to a different GM."""

    def setUp(self):
        from world.gm.constants import GMPromptKind
        from world.gm.prompt_services import route_narratable_event
        from world.gm.types import NarratableEvent

        self.sheet = CharacterSheetFactory()
        self.scene = SceneFactory()
        self.owner = AccountFactory()
        SceneOwnerParticipationFactory(scene=self.scene, account=self.owner)
        self.addressed_gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=self.addressed_gm)
        [self.narration_prompt] = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.MIRACLE,
                scene=self.scene,
                character_sheet=self.sheet,
                room_text="a wonder occurs",
            ),
            candidates=[self.addressed_gm],
        )

    def test_scene_owner_cannot_list_it(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(
            reverse("magic:dramatic-moment-suggestion-list"), {"scene": self.scene.pk}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["results"], [])

    def test_scene_owner_cannot_confirm_it(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            reverse(
                "magic:dramatic-moment-suggestion-confirm",
                kwargs={"pk": self.narration_prompt.pk},
            )
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, resp.data)

    def test_scene_owner_cannot_dismiss_it(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post(
            reverse(
                "magic:dramatic-moment-suggestion-dismiss",
                kwargs={"pk": self.narration_prompt.pk},
            )
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, resp.data)
        self.narration_prompt.refresh_from_db()
        self.assertEqual(self.narration_prompt.status, GMPromptStatus.PENDING)
