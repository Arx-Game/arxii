"""Participation is read off the log (#3867): a room-heard line enters a scene."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import InteractionMode, ScenePrivacyMode
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.participation import entered_sheet_ids, has_entered, keeps_a_log


class ParticipationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.other_scene = SceneFactory()
        cls.poser = CharacterSheetFactory()
        cls.speaker = CharacterSheetFactory()
        cls.emitter = CharacterSheetFactory()
        cls.whisperer = CharacterSheetFactory()
        cls.reader = CharacterSheetFactory()
        cls.elsewhere = CharacterSheetFactory()
        InteractionFactory(persona=cls.poser.primary_persona, scene=cls.scene, content="waves.")
        InteractionFactory(
            persona=cls.speaker.primary_persona,
            scene=cls.scene,
            mode=InteractionMode.SAY,
            content="Evening.",
        )
        InteractionFactory(
            persona=cls.emitter.primary_persona,
            scene=cls.scene,
            mode=InteractionMode.EMIT,
            content="The bells go quiet.",
        )
        InteractionFactory(
            persona=cls.whisperer.primary_persona,
            scene=cls.scene,
            mode=InteractionMode.WHISPER,
            content="psst",
        )
        InteractionFactory(
            persona=cls.elsewhere.primary_persona, scene=cls.other_scene, content="nods."
        )

    def test_a_pose_a_say_or_an_emit_enters_the_scene(self) -> None:
        assert entered_sheet_ids(self.scene) == {
            self.poser.pk,
            self.speaker.pk,
            self.emitter.pk,
        }
        assert has_entered(self.scene, self.poser.pk)
        assert has_entered(self.scene, self.speaker.pk)
        assert has_entered(self.scene, self.emitter.pk)

    def test_a_whisper_does_not_enter(self) -> None:
        assert not has_entered(self.scene, self.whisperer.pk)

    def test_a_reader_and_a_line_in_another_scene_do_not_enter(self) -> None:
        assert not has_entered(self.scene, self.reader.pk)
        assert not has_entered(self.scene, self.elsewhere.pk)
        assert has_entered(self.other_scene, self.elsewhere.pk)

    def test_an_ephemeral_scene_keeps_no_log(self) -> None:
        ephemeral = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        assert keeps_a_log(self.scene)
        assert not keeps_a_log(ephemeral)
