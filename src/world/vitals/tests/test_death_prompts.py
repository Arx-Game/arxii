from unittest import mock

from django.db import DatabaseError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind
from world.gm.models import GMPrompt
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals
from world.vitals.services import apply_pending_certain_death, defer_or_apply_certain_death


class DeathPromptTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.scene = SceneFactory()
        cls.gm = AccountFactory()
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)

    def setUp(self):
        # Factory bodies have location=None; pin the scene _mark_dead stamps as
        # died_in_scene (the offscreen test overrides this with None).
        patcher = mock.patch("world.vitals.services._active_scene_at_body", return_value=self.scene)
        patcher.start()
        self.addCleanup(patcher.stop)
        protection = mock.patch(
            "world.stories.npc_protection.is_death_prevented_by_story", return_value=False
        )
        protection.start()
        self.addCleanup(protection.stop)

    def test_immediate_death_prompts_the_gm(self):
        sheet = CharacterSheetFactory()
        with mock.patch("world.conditions.services.has_death_deferred", return_value=False):
            defer_or_apply_certain_death(sheet)
        self.assertTrue(
            GMPrompt.objects.filter(
                kind=GMPromptKind.DEATH, character_sheet=sheet, addressed_to=self.gm
            ).exists()
        )

    def test_martyr_prompted_when_the_death_lands_not_when_set(self):  # spec scenario 4
        sheet = CharacterSheetFactory()
        with mock.patch("world.conditions.services.has_death_deferred", return_value=True):
            self.assertTrue(defer_or_apply_certain_death(sheet))
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.DEATH).exists())
        with mock.patch("world.conditions.services.has_death_deferred", return_value=False):
            self.assertTrue(apply_pending_certain_death(sheet))
        self.assertTrue(
            GMPrompt.objects.filter(kind=GMPromptKind.DEATH, character_sheet=sheet).exists()
        )

    def test_offscreen_death_prompts_no_one(self):
        sheet = CharacterSheetFactory()
        with (
            mock.patch("world.conditions.services.has_death_deferred", return_value=False),
            mock.patch("world.vitals.services._active_scene_at_body", return_value=None),
        ):
            defer_or_apply_certain_death(sheet)
        self.assertFalse(GMPrompt.objects.filter(character_sheet=sheet).exists())

    def test_routing_database_error_does_not_lose_the_death(self):
        """A second scene GM makes the SECOND ``GMPrompt.objects.create`` raise.

        Proves the death still lands (life_state=DEAD, the write that matters)
        and the atomic wrap rolls the prompt batch back cleanly -- no orphan
        GMPrompt row and no live notify -- even though routing itself failed.
        With the try/except shape reverted, this raises out of
        ``defer_or_apply_certain_death`` instead of completing.
        """
        second_gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=second_gm)
        sheet = CharacterSheetFactory()

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
            mock.patch("world.conditions.services.has_death_deferred", return_value=False),
        ):
            defer_or_apply_certain_death(sheet)

        notify.assert_not_called()
        self.assertFalse(GMPrompt.objects.filter(character_sheet=sheet).exists())
        vitals = CharacterVitals.objects.get(character_sheet=sheet)
        self.assertEqual(vitals.life_state, CharacterLifeState.DEAD)
