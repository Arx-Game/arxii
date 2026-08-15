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

    def test_speaker_own_line_is_second_person(self) -> None:
        """M2 (#2993 final-review): the speaker's own echo reads 'You say ...',
        matching the $You() $conj(say) voice of the universal-language branch,
        not the third-person phrasing every other listener gets.
        """
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)

        with patch.object(speaker, "msg") as mock_msg:
            result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        sent_text = mock_msg.call_args_list[0].args[0]
        assert sent_text == f'You say in {self.language.name}, "{self.TEXT}"'

    def test_dreamside_occupant_excluded_from_language_say(self) -> None:
        """C2 (#2993 final-review): the language-tagged say branch hand-rolls room
        delivery instead of going through message_location()/msg_contents, so it
        must apply the same #2287 dreamside exclusion by hand or a dreamside-
        perceiving character illegitimately hears waking-room language chatter.

        Scoped to the telnet TEXT delivery this PR's per-recipient loop hand-rolls
        (a positional-string ``msg()`` call) -- the structured WS interaction
        payload (a kwarg-only ``msg(interaction=...)`` call from the pre-existing,
        out-of-scope ``push_interaction``/``_broadcast_to_location`` path) is not
        this fix's concern.

        Post-#2997: the say path routes through the broadcast-exclusion registry
        (``resolve_broadcast_exclusions``), which calls the real, still-registered
        ``_dreamside_occupants`` resolver by object reference -- patching the name
        in ``communication.py`` no longer intercepts it, so this patches
        ``perceives_dreamside`` (what ``_dreamside_occupants`` itself calls) instead.
        """
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        dreamer, dreamer_sheet = self._sheeted_character(room, key="Dreamer", fluency=100)

        def _fake_perceives_dreamside(sheet):
            return sheet is not None and sheet.pk == dreamer_sheet.pk

        with (
            patch(
                "world.vitals.services.perceives_dreamside",
                side_effect=_fake_perceives_dreamside,
            ),
            patch.object(dreamer, "msg") as mock_msg,
        ):
            result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        text_calls = [c for c in mock_msg.call_args_list if c.args]
        assert not text_calls, f"dreamer received telnet text delivery: {text_calls}"

    def test_second_registered_resolver_honored_by_language_say(self) -> None:
        """M1 (#2997 review fix): the language-say path must honor EVERY registered
        broadcast-exclusion resolver, not just the built-in dreamside one -- it calls
        ``resolve_broadcast_exclusions`` (the registry union), not
        ``_dreamside_occupants`` by name, so a second resolver (a future haunting/
        vision/glamour mechanism) is excluded here too.
        """
        from flows.service_functions import perception_registry

        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        haunted, _ = self._sheeted_character(room, key="Haunted", fluency=100)

        def _fake_resolver(location):
            return [haunted] if location == room else []

        original_resolvers = list(perception_registry._RESOLVERS)
        perception_registry.register_broadcast_exclusion(_fake_resolver)
        try:
            with patch.object(haunted, "msg") as mock_msg:
                result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)
        finally:
            perception_registry._RESOLVERS[:] = original_resolvers

        assert result.success is True
        text_calls = [c for c in mock_msg.call_args_list if c.args]
        assert not text_calls, f"haunted listener received telnet text delivery: {text_calls}"

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


class UniversalLanguageNormalizationTests(LanguageSpeechTestCase):
    """M3 (#2993 final-review): explicitly picking a universal language normalizes
    to the null 'universal/untagged' contract instead of stamping the real row, and
    a zero-fluency speaker can still explicitly speak it (no fluency gate applies).
    """

    TEXT = "the caravan leaves at dawn through the salt gate"

    def test_explicit_universal_language_id_stamps_none(self) -> None:
        universal_trait = Trait.objects.create(
            name="TestSpeechUniversalTongue",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        universal_language = LanguageFactory(
            name="TestSpeechUniversalTongue", trait=universal_trait, is_universal=True
        )
        room = _make_room()
        # Deliberately zero fluency — a universal tongue needs none to speak it.
        speaker, _ = self._sheeted_character(room, key="Speaker")

        result = SayAction().run(speaker, text=self.TEXT, language_id=universal_language.pk)

        assert result.success is True
        interaction = Interaction.objects.get(content=self.TEXT)
        self.assertIsNone(interaction.language_id)


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
