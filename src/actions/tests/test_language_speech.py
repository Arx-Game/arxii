"""Tests for Task 5 (#2993): say/whisper/mutter speak languages, per-listener delivery."""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.communication import (
    EmitAction,
    MutterAction,
    PoseAction,
    SayAction,
    WhisperAction,
)
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import expire_scene_scoped_conditions
from world.mechanics.models import ModifierTarget
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction
from world.species.factories import LanguageFactory
from world.species.tests.test_language_comprehension import (
    make_language_with_target,
    make_understanding_condition,
)
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
        # out of scope here. The line echoes an Interaction, so it arrives as
        # Evennia's ``(text, {options})`` form (#3933).
        sent_text, _sent_options = mock_msg.call_args_list[0].args[0]
        assert sent_text == f'{speaker.key} says in {self.language.name}, "{self.TEXT}"'

    def test_zero_fluency_listener_sees_garbled_text(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        listener, _ = self._sheeted_character(room, key="IgnorantListener")

        with patch.object(listener, "msg") as mock_msg:
            result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        sent_text, _sent_options = mock_msg.call_args_list[0].args[0]
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
        sent_text, _sent_options = mock_msg.call_args_list[0].args[0]
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

    def test_language_tagged_delivery_is_tagged_as_an_interaction_echo(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        self._sheeted_character(room, key="Listener", fluency=100)

        with patch("actions.definitions.communication.send_message") as mock_send:
            result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)

        assert result.success is True
        assert mock_send.call_count == 2
        for call in mock_send.call_args_list:
            assert call.kwargs["echo_of"] == InteractionMode.SAY

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
        sent_text, _sent_options = mock_msg.call_args_list[0].args[0]
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
        # record_mutter_interaction() writes the full text first, then the
        # fragment. Identify them by that order, never by content: the
        # fragment is a SystemRandom word-survival garble that keeps every
        # word of a four-word line about 1 time in 81, and an equal-content
        # lookup then matches both rows.
        full, fragment = Interaction.objects.filter(mode=InteractionMode.MUTTER).order_by("pk")
        assert full.content == "the plan is set"
        assert full.language_id == self.language.pk
        assert fragment.language_id is None

    def test_mutter_delivery_is_tagged_as_an_interaction_echo(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Speaker", fluency=100)
        receiver, _ = self._sheeted_character(room, key="Receiver")
        self._sheeted_character(room, key="Bystander")

        with patch("actions.definitions.communication.send_message") as mock_send:
            result = MutterAction().run(
                speaker, text="the plan is set", receivers=[receiver], language_id=self.language.pk
            )

        assert result.success is True
        assert mock_send.call_count == 2
        for call in mock_send.call_args_list:
            assert call.kwargs["echo_of"] == InteractionMode.MUTTER

    def test_mutter_speaker_without_the_language_fails(self) -> None:
        room = _make_room()
        speaker, _ = self._sheeted_character(room, key="Ignorant")
        receiver, _ = self._sheeted_character(room, key="Receiver")

        result = MutterAction().run(
            speaker, text="the plan is set", receivers=[receiver], language_id=self.language.pk
        )

        assert result.success is False


class ConditionComprehensionLiveTests(TestCase):
    """#4090: a listener's active condition raises comprehension on live delivery."""

    TEXT = "the north gate opens at the second bell so bring the lamp oil"

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        CharacterTraitValue.flush_instance_cache()
        self.language, self.target = make_language_with_target("LiveCompTongue")
        self.condition = make_understanding_condition("Placeholder Live Understanding", self.target)
        self.room = _make_room()
        self.speaker = CharacterFactory(db_key="Envoy", location=self.room)
        self.speaker_sheet = CharacterSheetFactory(character=self.speaker)
        self.speaker_fluency = CharacterTraitValue.objects.create(
            character=self.speaker_sheet, trait=self.language.trait, value=100
        )
        self.listener = CharacterFactory(db_key="Wren", location=self.room)
        self.listener_sheet = CharacterSheetFactory(character=self.listener)

    def _heard(self) -> str:
        with patch.object(self.listener, "msg") as mock_msg:
            result = SayAction().run(self.speaker, text=self.TEXT, language_id=self.language.pk)
        assert result.success is True
        sent_text, _options = mock_msg.call_args_list[0].args[0]
        return sent_text

    def _ws_content(self) -> str:
        with patch.object(self.listener, "msg") as mock_msg:
            SayAction().run(self.speaker, text=self.TEXT, language_id=self.language.pk)
        payloads = [call.kwargs for call in mock_msg.call_args_list if "interaction" in call.kwargs]
        return payloads[-1]["interaction"][1]["content"]

    def test_strong_condition_reads_clear_on_telnet_and_ws(self) -> None:
        ConditionInstanceFactory(target=self.listener, condition=self.condition, severity=4)
        assert self._heard() == f'Envoy says in {self.language.name}, "{self.TEXT}"'
        assert self._ws_content() == self.TEXT

    def test_weak_condition_reads_partly_garbled(self) -> None:
        ConditionInstanceFactory(target=self.listener, condition=self.condition, severity=2)
        heard = self._heard()
        assert heard.startswith(f'Envoy says in {self.language.name}, "')
        assert "..." in heard
        assert heard != f'Envoy says in {self.language.name}, "{self.TEXT}"'

    def test_without_condition_garbles_entirely(self) -> None:
        assert self._heard() == f'Envoy says in {self.language.name}, "..."'

    def test_condition_does_not_let_the_listener_speak(self) -> None:
        ConditionInstanceFactory(target=self.listener, condition=self.condition, severity=4)
        result = SayAction().run(self.listener, text="hello", language_id=self.language.pk)
        assert result.success is False
        assert result.message == "You don't know that tongue."

    def test_speaker_under_condition_is_heard_at_trained_level(self) -> None:
        """F5: a condition on the SPEAKER does not lift their band; listeners hear trained."""
        self.speaker_fluency.value = 20
        self.speaker_fluency.save(update_fields=["value"])
        ConditionInstanceFactory(target=self.speaker, condition=self.condition, severity=4)
        CharacterTraitValue.objects.create(
            character=self.listener_sheet, trait=self.language.trait, value=100
        )
        heard = self._heard()
        assert "..." in heard
        assert heard != f'Envoy says in {self.language.name}, "{self.TEXT}"'
        assert self._ws_content() != self.TEXT

    def test_scene_sweep_ends_the_effect(self) -> None:
        scene_condition = ConditionTemplateFactory(
            name="Placeholder Scene Understanding", default_duration_type=DurationType.SCENE
        )
        ConditionModifierEffectFactory(
            condition=scene_condition, modifier_target=self.target, value=80
        )
        ConditionInstanceFactory(target=self.listener, condition=scene_condition)
        assert self._heard() == f'Envoy says in {self.language.name}, "{self.TEXT}"'
        expire_scene_scoped_conditions([self.listener])
        assert self._heard() == f'Envoy says in {self.language.name}, "..."'


class GarbleScopeTests(TestCase):
    """Decision 9: poses and emits are never language-tagged, so never garbled."""

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        self.language, _target = make_language_with_target("ScopeTongue")
        room = _make_room()
        self.speaker = CharacterFactory(db_key="Envoy", location=room)
        sheet = CharacterSheetFactory(character=self.speaker)
        CharacterTraitValue.objects.create(character=sheet, trait=self.language.trait, value=100)
        sheet.current_language = self.language
        sheet.save(update_fields=["current_language"])

    def test_pose_emit_and_tagged_pose_store_no_language(self) -> None:
        PoseAction().run(self.speaker, text="sets both hands flat on the table.")
        PoseAction().run(
            self.speaker, text="looks to each face in turn.", language_id=self.language.pk
        )
        EmitAction().run(self.speaker, text="A bell tolls somewhere below.")
        for content in (
            "sets both hands flat on the table.",
            "looks to each face in turn.",
            "A bell tolls somewhere below.",
        ):
            assert Interaction.objects.get(content=content).language_id is None
