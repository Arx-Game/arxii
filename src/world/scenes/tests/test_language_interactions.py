"""Tests for Task 4 (#2993): Interaction.language + CharacterSheet.current_language

model/service persistence. Real per-recipient WS-render assertions live in Task 5's
action tests, where rooms/audiences exist end-to-end — this module stays scoped to
the model fields and the record/create plumbing.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction, record_interaction
from world.species.factories import LanguageFactory


class TestInteractionLanguageField(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.language = LanguageFactory(name="TestKhatic")

    def test_create_interaction_persists_language(self) -> None:
        char_a = CharacterFactory(db_key="Alice")
        sheet_a = CharacterSheetFactory(character=char_a)

        interaction = create_interaction(
            persona=sheet_a.primary_persona,
            content="Ktha vess morren.",
            mode=InteractionMode.SAY,
            language=self.language,
        )
        interaction.refresh_from_db()
        self.assertEqual(interaction.language_id, self.language.pk)

    def test_create_interaction_defaults_language_to_none(self) -> None:
        char_a = CharacterFactory(db_key="Alice")
        sheet_a = CharacterSheetFactory(character=char_a)

        interaction = create_interaction(
            persona=sheet_a.primary_persona,
            content="waves.",
            mode=InteractionMode.POSE,
        )
        self.assertIsNone(interaction.language_id)


class TestRecordInteractionLanguage(TestCase):
    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)
        self.language = LanguageFactory(name="TestRecordKhatic")

    def test_record_interaction_stamps_language(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        CharacterSheetFactory(character=char_a)
        CharacterSheetFactory(character=char_b)

        result = record_interaction(
            character=char_a,
            content="Ktha vess morren.",
            mode=InteractionMode.SAY,
            language=self.language,
        )
        assert result is not None
        self.assertEqual(result.language_id, self.language.pk)

    def test_record_interaction_without_language_stays_none(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterSheetFactory(character=char_a)

        result = record_interaction(
            character=char_a,
            content="strides in.",
            mode=InteractionMode.POSE,
        )
        assert result is not None
        self.assertIsNone(result.language_id)


class TestCharacterSheetCurrentLanguage(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.language = LanguageFactory(name="TestSheetKhatic")

    def test_defaults_to_none(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertIsNone(sheet.current_language)

    def test_set_and_read_round_trip(self) -> None:
        sheet = CharacterSheetFactory()
        sheet.current_language = self.language
        sheet.save(update_fields=["current_language"])
        sheet.refresh_from_db()
        self.assertEqual(sheet.current_language, self.language)
