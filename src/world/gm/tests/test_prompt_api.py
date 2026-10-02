"""The GM prompt queue API (#4101 Task 9): visibility, confirm, dismiss, narrate, filters."""

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.factories import GMProfileFactory, GMPromptFactory
from world.gm.models import GMPromptFilter, GMPromptNarration
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
)
from world.magic.models import ResonanceGrant
from world.magic.models.dramatic_moment import DramaticMomentTag
from world.scenes.factories import (
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
)

URL = "/api/gm/prompts/"


class GMPromptApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.scene = SceneFactory()
        cls.gm = AccountFactory()
        GMProfileFactory(account=cls.gm)
        cls.other_gm = AccountFactory()
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)
        SceneGMParticipationFactory(scene=cls.scene, account=cls.other_gm)
        cls.owner_player = AccountFactory()
        SceneOwnerParticipationFactory(scene=cls.scene, account=cls.owner_player)
        cls.crosser = CharacterSheetFactory()
        cls.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=cls.scene,
            character_sheet=cls.crosser,
            addressed_to=cls.gm,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="room",
        )
        cls.stake_prompt = GMPromptFactory(
            kind=GMPromptKind.STAKE_OUTCOME,
            scene=None,
            character_sheet=None,
            addressed_to=cls.gm,
            moment_type=None,
            success_level=None,
        )
        cls.moment = GMPromptFactory(scene=cls.scene)  # dramatic_moment kind

    def _client(self, account):
        client = APIClient()
        client.force_authenticate(account)
        return client

    def _ids(self, account):
        resp = self._client(account).get(URL, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 200)
        return {row["id"] for row in resp.data["results"]}

    def test_addressed_gm_sees_scene_and_sceneless_prompts(self):
        self.assertEqual(self._ids(self.gm), {self.prompt.pk, self.stake_prompt.pk, self.moment.pk})

    def test_other_gm_never_sees_my_prompt(self):
        self.assertEqual(self._ids(self.other_gm), {self.moment.pk})

    def test_scene_owner_player_never_sees_narration_prompts(self):
        self.assertEqual(self._ids(self.owner_player), {self.moment.pk})

    def test_subject_player_sees_nothing(self):
        stranger = AccountFactory()
        resp = self._client(stranger).get(URL, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 403)

    def test_gm_who_muted_moments_does_not_see_them(self):
        GMPrompt = type(self.moment)
        muter = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=muter)
        GMPromptFilter.objects.create(
            account=muter, group=GMPromptGroup.DRAMATIC_MOMENT, enabled=False
        )
        self.assertNotIn(self.moment.pk, self._ids(muter))
        self.assertTrue(GMPrompt.objects.filter(pk=self.moment.pk).exists())

    def test_private_text_only_in_the_addressed_gms_payload(self):
        resp = self._client(self.gm).get(URL, {"scene": self.scene.pk})
        row = next(r for r in resp.data["results"] if r["id"] == self.prompt.pk)
        self.assertEqual(row["private_text"], "vision")

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_dismiss_narration_releases(self, narrate):
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            private_text="x",
        )
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._client(self.gm).post(f"{URL}{prompt.pk}/dismiss/")
        self.assertEqual(resp.status_code, 200)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once()

    def test_narrate_room_links(self):
        with (
            mock.patch("world.gm.views.character_for_request", return_value=self._gm_character()),
            mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene),
        ):
            resp = self._client(self.gm).post(
                f"{URL}{self.prompt.pk}/narrate/",
                {"text": "The floor groans.", "audience": "room"},
                format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(GMPromptNarration.objects.filter(prompt=self.prompt).exists())

    def test_narrate_chosen_refused_without_gm_trust_returns_400(self):
        untrusted = AccountFactory()  # scene GM by participation, no GMProfile, not staff
        SceneGMParticipationFactory(scene=self.scene, account=untrusted)
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=untrusted,
            moment_type=None,
            success_level=None,
        )
        char = CharacterSheetFactory().character
        char.account = untrusted
        with (
            mock.patch("world.gm.views.character_for_request", return_value=char),
            mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene),
        ):
            resp = self._client(untrusted).post(
                f"{URL}{prompt.pk}/narrate/",
                {
                    "text": "x",
                    "audience": "chosen",
                    "receiver_persona_ids": [self.crosser.primary_persona.pk],
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)
        self.assertFalse(GMPromptNarration.objects.filter(prompt=prompt).exists())

    def test_filters_list_five_groups_and_set(self):
        client = self._client(self.gm)
        rows = client.get("/api/gm/prompt-filters/").data
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r["enabled"] for r in rows))
        resp = client.post(
            "/api/gm/prompt-filters/set/", {"group": "miracle", "enabled": False}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            GMPromptFilter.objects.get(account=self.gm, group=GMPromptGroup.MIRACLE).enabled
        )

    def _gm_character(self):
        char = CharacterSheetFactory().character
        char.account = self.gm
        return char


class GMPromptDramaticMomentConfirmDismissTest(TestCase):
    """POST .../{id}/confirm/ and .../{id}/dismiss/ on a dramatic_moment prompt (#2183,
    ported from the retired ``world.magic.tests.test_suggestion_api`` module — unchanged
    in substance, now against the one GMPromptViewSet queue instead of the retired
    per-app suggestion inbox)."""

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

    def _client(self, account):
        client = APIClient()
        client.force_authenticate(account)
        return client

    def _url(self, action: str, suggestion_id: int | None = None) -> str:
        return f"{URL}{suggestion_id or self.suggestion.pk}/{action}/"

    def test_gm_confirms_mints_tag_and_grants_resonance(self):
        resp = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(resp.status_code, 200, resp.data)
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
        resp = self._client(self.gm).post(self._url("dismiss"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.DISMISSED)
        self.assertIsNone(self.suggestion.confirmed_tag)

    def test_non_gm_participant_confirm_is_forbidden(self):
        participant = AccountFactory()
        resp = self._client(participant).post(self._url("confirm"))
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("detail", resp.data)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.PENDING)

    def test_confirm_after_cap_returns_400_with_user_message(self):
        DramaticMomentTagFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )
        resp = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("detail", resp.data)
        self.assertTrue(resp.data["detail"])
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.PENDING)

    def test_double_confirm_returns_400(self):
        first = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(first.status_code, 200, first.data)
        second = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(second.status_code, 400, second.data)
        self.assertIn("detail", second.data)
        self.assertTrue(second.data["detail"])
