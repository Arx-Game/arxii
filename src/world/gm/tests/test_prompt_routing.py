"""Event routing to the GM prompt queue (#4101 Task 2): the spec's test seams."""

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.factories import GMPromptFilterFactory
from world.gm.models import GMPrompt
from world.gm.prompt_services import (
    dismiss_gm_prompt,
    prompt_recipients,
    route_narratable_event,
)
from world.gm.types import NarratableEvent
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction
from world.scenes.scene_admin_services import finish_scene_full


class RouteNarratableEventTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gm = AccountFactory()
        cls.second_gm = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.scene = SceneFactory()
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)
        cls.quiet_scene = SceneFactory()

    def _event(self, scene, kind=GMPromptKind.MIRACLE, **kw):
        return NarratableEvent(kind=kind, scene=scene, character_sheet=self.sheet, **kw)

    def test_event_with_gm_creates_prompt_and_skips_delivery(self):
        deliver = mock.Mock()
        prompts = route_narratable_event(
            self._event(self.scene, room_text="authored"), deliver_unprompted=deliver
        )
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].addressed_to, self.gm)
        self.assertEqual(prompts[0].room_text, "authored")
        self.assertEqual(prompts[0].status, GMPromptStatus.PENDING)
        deliver.assert_not_called()

    def test_no_gm_delivers_as_today_and_creates_nothing(self):
        deliver = mock.Mock()
        prompts = route_narratable_event(self._event(self.quiet_scene), deliver_unprompted=deliver)
        self.assertEqual(prompts, [])
        deliver.assert_called_once()
        self.assertFalse(GMPrompt.objects.filter(scene=self.quiet_scene).exists())

    def test_filtered_out_kind_creates_no_prompt(self):
        muted_scene = SceneFactory()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=muted_scene, account=gm)
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.MIRACLE, enabled=False)
        deliver = mock.Mock()
        self.assertEqual(
            route_narratable_event(self._event(muted_scene), deliver_unprompted=deliver), []
        )
        deliver.assert_called_once()

    def test_mute_is_per_group(self):
        gm = AccountFactory()
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.MIRACLE, enabled=False)
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        self.assertEqual(prompt_recipients(scene, GMPromptKind.DEATH), [gm])

    def test_two_gms_one_muted(self):
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        SceneGMParticipationFactory(scene=scene, account=self.second_gm)
        GMPromptFilterFactory(account=self.second_gm, group=GMPromptGroup.MIRACLE, enabled=False)
        prompts = route_narratable_event(self._event(scene))
        self.assertEqual([p.addressed_to for p in prompts], [self.gm])

    def test_departed_gm_is_not_prompted(self):
        scene = SceneFactory()
        part = SceneGMParticipationFactory(scene=scene, account=AccountFactory())
        part.left_at = part.joined_at
        part.save()
        self.assertEqual(prompt_recipients(scene, GMPromptKind.DEATH), [])

    def test_explicit_candidates_still_filtered(self):
        gm = AccountFactory()
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.STAKE_OUTCOME, enabled=False)
        self.assertEqual(prompt_recipients(None, GMPromptKind.STAKE_OUTCOME, candidates=[gm]), [])

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_dismiss_releases_private_default(self, narrate):
        prompt = route_narratable_event(
            self._event(self.scene, kind=GMPromptKind.CROSSING, private_text="vision")
        )[0]
        dismiss_gm_prompt(prompt, resolver=self.gm)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once_with(self.sheet.character, "vision")

    def test_finish_scene_releases_pending_private_default(self):
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        route_narratable_event(
            self._event(scene, kind=GMPromptKind.CROSSING, private_text="the vision")
        )
        finish_scene_full(scene)
        prompt = GMPrompt.objects.get(scene=scene)
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.assertTrue(
            Interaction.objects.filter(
                content="the vision",
                mode=InteractionMode.WHISPER,
                receivers__persona=self.sheet.primary_persona,
            ).exists()
        )
