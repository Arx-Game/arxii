"""Tests for Task 5 (#2993): say/whisper/mutter speak languages, per-listener delivery."""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.communication import MutterAction, SayAction, WhisperAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.models import Interaction
from world.species.factories import LanguageFactory
from world.traits.models import CharacterTraitValue, Trait, TraitCategory, TraitType


def _make_room():
    return ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")


class LanguageSpeechTestCase(TestCase):
    """Shared fixtures: a language with a real trait, and a sheeted-character helper."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.trait = Trait.objects.create(
            name="TestSpeechKhatic",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.language = LanguageFactory(name="TestSpeechKhatic", trait=cls.trait)

    def _sheeted_character(self, room, *, key, fluency=None):
        character = CharacterFactory(db_key=key, location=room)
        sheet = CharacterSheetFactory(character=character)
        if fluency is not None:
            CharacterTraitValue.objects.create(character=sheet, trait=self.trait, value=fluency)
        return character, sheet


class SayActionLanguageTests(LanguageSpeechTestCase):
    TEXT = "the caravan leaves at dawn through the salt gate"

    def test_fluent_listener_sees_full_tagged_text(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        listener, _ = self._sheeted_character(room, key="FluentListener", fluency=100)

        with patch.object(listener, "msg") as mock_msg:
            result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        # The telnet text delivery is the first msg() call; a second call carries
        # the structured WS interaction payload (push_interaction, Task 4) and is
        # out of scope here.
        sent_text = mock_msg.call_args_list[0].args[0]
        assert sent_text == f'{speaker.key} says in {self.language.name}, "{self.TEXT}"'

    def test_zero_fluency_listener_sees_garbled_text(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        listener, _ = self._sheeted_character(room, key="IgnorantListener")

        with patch.object(listener, "msg") as mock_msg:
            result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        sent_text = mock_msg.call_args_list[0].args[0]
        assert self.TEXT not in sent_text
        assert "..." in sent_text

    def test_recorded_interaction_has_language(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)

        result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        interaction = Interaction.objects.get(content=self.TEXT)
        assert interaction.language_id == self.language.pk

    def test_speaker_without_the_language_fails(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Ignorant")

        result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is False
        assert not Interaction.objects.filter(content=self.TEXT).exists()

    def test_say_with_no_language_matches_legacy_broadcast(self) -> None:
        room = _make_room()
        speaker = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        with patch("actions.definitions.communication.message_location") as mock_broadcast:
            result = SayAction().run(speaker, text="hello")

        assert result.success is True
        assert mock_broadcast.call_count == 1
        call_args = mock_broadcast.call_args.args
        assert call_args[1] == '$You() $conj(say) "hello"'

    def test_language_id_kwarg_beats_current_language(self) -> None:
        room = _make_room()
        other_trait = Trait.objects.create(
            name="TestSpeechOtherTongue",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        other_language = LanguageFactory(name="TestSpeechOtherTongue", trait=other_trait)

        speaker, speaker_sheet = self._sheeted_character(room, key="Speaker", fluency=100)
        CharacterTraitValue.objects.create(character=speaker_sheet, trait=other_trait, value=100)
        speaker_sheet.current_language = other_language
        speaker_sheet.save(update_fields=["current_language"])

        result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        interaction = Interaction.objects.get(content=self.TEXT)
        assert interaction.language_id == self.language.pk


class WhisperActionLanguageTests(LanguageSpeechTestCase):
    def test_whisper_stamps_language_and_stays_full_text(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        target, _ = self._sheeted_character(room, key="Target")

        with patch.object(target, "msg") as mock_msg:
            result = WhisperAction().run(
                speaker, target=target, text="secret", language_id=self.language.pk
            )

        assert result.success is True
        sent_text = mock_msg.call_args_list[0].args[0]
        assert "secret" in sent_text
        interaction = Interaction.objects.get(content="secret")
        assert interaction.language_id == self.language.pk

    def test_whisper_speaker_without_the_language_fails(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Ignorant")
        target, _ = self._sheeted_character(room, key="Target")

        result = WhisperAction().run(
            speaker, target=target, text="secret", language_id=self.language.pk
        )

        assert result.success is False


class MutterActionLanguageTests(LanguageSpeechTestCase):
    def test_mutter_stamps_language_on_full_text_only(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        receiver, _ = self._sheeted_character(room, key="Receiver")

        result = MutterAction().run(
            speaker, text="the plan is set", receivers=[receiver], language_id=self.language.pk
        )

        assert result.success is True
        full = Interaction.objects.get(content="the plan is set")
        assert full.language_id == self.language.pk
        fragment = Interaction.objects.exclude(pk=full.pk).latest("timestamp")
        assert fragment.language_id is None

    def test_mutter_speaker_without_the_language_fails(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Ignorant")
        receiver, _ = self._sheeted_character(room, key="Receiver")

        result = MutterAction().run(
            speaker, text="the plan is set", receivers=[receiver], language_id=self.language.pk
        )

        assert result.success is False
