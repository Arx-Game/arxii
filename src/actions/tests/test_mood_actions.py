"""Tests for #2994: SetMoodAction, SenseMoodAction, CmdFeel arg resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.mood import (
    MOOD_SENSE_CHECK_TYPE_NAME,
    SenseMoodAction,
    SetMoodAction,
)
from commands.exceptions import CommandError
from commands.mood import CmdFeel
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory, MoodOptionFactory
from world.checks.factories import CheckTypeFactory
from world.skills.factories import CharacterSpecializationValueFactory, SpecializationFactory


def _make_room():
    return ObjectDBFactory(db_key="MoodActionRoom", db_typeclass_path="typeclasses.rooms.Room")


def _make_cmd(cls, caller, args=""):
    """Mirror actions/tests/test_language_actions.py's `_make_cmd` helper."""
    cmd = cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd.key} {args}"
    cmd.cmdname = cmd.key
    return cmd


class SetMoodActionTests(TestCase):
    def _sheeted_character(self, room, *, key):
        character = CharacterFactory(db_key=key, location=room)
        sheet = CharacterSheetFactory(character=character)
        return character, sheet

    def test_happy_path_sets_current_mood(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Feeler")
        mood = MoodOptionFactory(name="Angry")

        result = SetMoodAction().run(speaker, mood_id=mood.pk)

        assert result.success is True
        assert result.message == "You feel angry."
        sheet.refresh_from_db()
        assert sheet.current_mood_id == mood.pk

    def test_omitted_mood_id_clears_it(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Feeler")
        mood = MoodOptionFactory(name="Sad")
        sheet.current_mood = mood
        sheet.save(update_fields=["current_mood"])

        result = SetMoodAction().run(speaker)

        assert result.success is True
        assert result.message == "Your feelings settle."
        sheet.refresh_from_db()
        assert sheet.current_mood_id is None

    def test_inactive_mood_rejected(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Feeler")
        mood = MoodOptionFactory(name="Retired", is_active=False)

        result = SetMoodAction().run(speaker, mood_id=mood.pk)

        assert result.success is False
        assert result.message == "There is no such mood."
        sheet.refresh_from_db()
        assert sheet.current_mood_id is None

    def test_unknown_mood_id_rejected(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Feeler")

        result = SetMoodAction().run(speaker, mood_id=999999)

        assert result.success is False
        assert result.message == "There is no such mood."
        sheet.refresh_from_db()
        assert sheet.current_mood_id is None

    def test_silent_no_room_broadcast(self) -> None:
        """INTERNAL and SILENT (spec amendment 1): setting a mood never broadcasts."""
        room = _make_room()
        speaker, _sheet = self._sheeted_character(room, key="Feeler")
        mood = MoodOptionFactory(name="Calm")

        with (
            patch("flows.service_functions.communication.message_location") as mock_broadcast,
            patch(
                "world.scenes.interaction_services.record_interaction"
            ) as mock_record_interaction,
        ):
            result = SetMoodAction().run(speaker, mood_id=mood.pk)

        assert result.success is True
        mock_broadcast.assert_not_called()
        mock_record_interaction.assert_not_called()


class SenseMoodActionTests(TestCase):
    def _sheeted_character(self, room, *, key):
        character = CharacterFactory(db_key=key, location=room)
        sheet = CharacterSheetFactory(character=character)
        return character, sheet

    def test_no_empathy_specialization_fails_cleanly(self) -> None:
        room = _make_room()
        actor, _actor_sheet = self._sheeted_character(room, key="Senser")
        target, _target_sheet = self._sheeted_character(room, key="Target")

        result = SenseMoodAction().run(actor, target=target)

        assert result.success is False
        assert result.message == "You lack the empathy to read others."

    def test_with_specialization_but_no_check_type_fails_cleanly(self) -> None:
        room = _make_room()
        actor, actor_sheet = self._sheeted_character(room, key="Senser")
        target, _target_sheet = self._sheeted_character(room, key="Target")
        empathy = SpecializationFactory(name="Empathy")
        CharacterSpecializationValueFactory(character=actor_sheet, specialization=empathy, value=10)

        result = SenseMoodAction().run(actor, target=target)

        assert result.success is False
        assert "isn't yours to draw on yet" in result.message

    def test_success_reveals_target_mood(self) -> None:
        room = _make_room()
        actor, actor_sheet = self._sheeted_character(room, key="Senser")
        target, target_sheet = self._sheeted_character(room, key="Target")
        empathy = SpecializationFactory(name="Empathy")
        CharacterSpecializationValueFactory(character=actor_sheet, specialization=empathy, value=10)
        CheckTypeFactory(name=MOOD_SENSE_CHECK_TYPE_NAME)
        mood = MoodOptionFactory(name="Flirty")
        target_sheet.current_mood = mood
        target_sheet.save(update_fields=["current_mood"])

        successful_check = MagicMock()
        successful_check.success_level = 1

        with patch("world.checks.services.perform_check", return_value=successful_check):
            result = SenseMoodAction().run(actor, target=target)

        assert result.success is True
        assert result.message == "You sense that Target feels flirty."

    def test_success_with_no_declared_mood_reports_settled(self) -> None:
        room = _make_room()
        actor, actor_sheet = self._sheeted_character(room, key="Senser")
        target, _target_sheet = self._sheeted_character(room, key="Target")
        empathy = SpecializationFactory(name="Empathy")
        CharacterSpecializationValueFactory(character=actor_sheet, specialization=empathy, value=10)
        CheckTypeFactory(name=MOOD_SENSE_CHECK_TYPE_NAME)

        successful_check = MagicMock()
        successful_check.success_level = 1

        with patch("world.checks.services.perform_check", return_value=successful_check):
            result = SenseMoodAction().run(actor, target=target)

        assert result.success is True
        assert result.message == "You sense that Target's feelings are settled."

    def test_failure_gives_vague_miss_message(self) -> None:
        room = _make_room()
        actor, actor_sheet = self._sheeted_character(room, key="Senser")
        target, target_sheet = self._sheeted_character(room, key="Target")
        empathy = SpecializationFactory(name="Empathy")
        CharacterSpecializationValueFactory(character=actor_sheet, specialization=empathy, value=10)
        CheckTypeFactory(name=MOOD_SENSE_CHECK_TYPE_NAME)
        mood = MoodOptionFactory(name="Angry")
        target_sheet.current_mood = mood
        target_sheet.save(update_fields=["current_mood"])

        failed_check = MagicMock()
        failed_check.success_level = -1

        with patch("world.checks.services.perform_check", return_value=failed_check):
            result = SenseMoodAction().run(actor, target=target)

        assert result.success is False
        assert result.message == "You can't get a read on them right now."

    def test_target_never_receives_a_message(self) -> None:
        """SILENT to the target in every outcome -- only the actor's ActionResult carries text."""
        room = _make_room()
        actor, actor_sheet = self._sheeted_character(room, key="Senser")
        target, _target_sheet = self._sheeted_character(room, key="Target")
        empathy = SpecializationFactory(name="Empathy")
        CharacterSpecializationValueFactory(character=actor_sheet, specialization=empathy, value=10)
        CheckTypeFactory(name=MOOD_SENSE_CHECK_TYPE_NAME)

        successful_check = MagicMock()
        successful_check.success_level = 1

        with (
            patch("world.checks.services.perform_check", return_value=successful_check),
            patch("flows.service_functions.communication.message_location") as mock_broadcast,
            patch.object(target, "msg") as mock_target_msg,
        ):
            SenseMoodAction().run(actor, target=target)

        mock_broadcast.assert_not_called()
        mock_target_msg.assert_not_called()


class CmdFeelTests(TestCase):
    def test_no_args_returns_empty_kwargs(self) -> None:
        room = _make_room()
        caller = ObjectDBFactory(
            db_key="Feeler", db_typeclass_path="typeclasses.characters.Character", location=room
        )
        cmd = _make_cmd(CmdFeel, caller, args="")

        kwargs = cmd.resolve_action_args()

        assert kwargs == {}

    def test_known_mood_resolves_to_pk(self) -> None:
        room = _make_room()
        caller = ObjectDBFactory(
            db_key="Feeler", db_typeclass_path="typeclasses.characters.Character", location=room
        )
        mood = MoodOptionFactory(name="Happy")
        cmd = _make_cmd(CmdFeel, caller, args="happy")

        kwargs = cmd.resolve_action_args()

        assert kwargs == {"mood_id": mood.pk}

    def test_unknown_mood_raises_naming_it(self) -> None:
        room = _make_room()
        caller = ObjectDBFactory(
            db_key="Feeler", db_typeclass_path="typeclasses.characters.Character", location=room
        )
        cmd = _make_cmd(CmdFeel, caller, args="nonexistentia")

        with self.assertRaises(CommandError) as ctx:
            cmd.resolve_action_args()
        assert "nonexistentia" in str(ctx.exception)
