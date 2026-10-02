from unittest import mock

from django.db import DatabaseError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptGroup, GMPromptKind
from world.gm.factories import GMPromptFilterFactory
from world.gm.models import GMPrompt
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction
from world.worship.factories import MiracleFactory, WorshippedBeingFactory
from world.worship.services import perform_divine_intervention


class MiracleNarrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.being = WorshippedBeingFactory(resonance_pool=10_000)
        cls.miracle = MiracleFactory(being=cls.being, narrative_text="A warmth answers.")

    def test_no_gm_goes_out_as_today(self):  # spec scenario 3
        sheet = CharacterSheetFactory()
        scene = SceneFactory()
        perform_divine_intervention(sheet, self.being, self.miracle, scene=scene)
        self.assertTrue(
            Interaction.objects.filter(
                content="A warmth answers.", mode=InteractionMode.EMIT, scene=scene
            ).exists()
        )

    def test_gm_present_prompts(self):
        sheet = CharacterSheetFactory()
        scene = SceneFactory()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        perform_divine_intervention(sheet, self.being, self.miracle, scene=scene)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.MIRACLE, addressed_to=gm)
        self.assertEqual(prompt.room_text, "A warmth answers.")
        self.assertFalse(
            Interaction.objects.filter(scene=scene, content="A warmth answers.").exists()
        )

    def test_gm_muted_miracles_goes_out_as_authored(self):  # spec scenario 6
        sheet = CharacterSheetFactory()
        scene = SceneFactory()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.MIRACLE, enabled=False)
        perform_divine_intervention(sheet, self.being, self.miracle, scene=scene)
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.MIRACLE).exists())
        self.assertTrue(
            Interaction.objects.filter(scene=scene, content="A warmth answers.").exists()
        )

    def test_routing_database_error_falls_back_to_unprompted_delivery_once(self):
        """With TWO candidate GMs, the SECOND ``GMPrompt.objects.create`` raises --
        proving ``route_narratable_event``'s atomic wrap rolls the whole batch back
        (the first GM's already-created prompt doesn't survive as an orphan). No GM
        notify fires, and the fallback delivers the authored line exactly once."""
        sheet = CharacterSheetFactory()
        scene = SceneFactory()
        gm = AccountFactory()
        second_gm = AccountFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        SceneGMParticipationFactory(scene=scene, account=second_gm)

        original_create = GMPrompt.objects.create
        calls = {"n": 0}

        def _raise_on_second(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                msg = "boom"
                raise DatabaseError(msg)
            return original_create(*args, **kwargs)

        with (
            mock.patch.object(GMPrompt.objects, "create", side_effect=_raise_on_second),
            mock.patch("world.gm.prompt_services.notify_gm_prompt") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            perform_divine_intervention(sheet, self.being, self.miracle, scene=scene)

        notify.assert_not_called()
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.MIRACLE).exists())
        self.assertEqual(
            Interaction.objects.filter(
                scene=scene, content="A warmth answers.", mode=InteractionMode.EMIT
            ).count(),
            1,
        )
