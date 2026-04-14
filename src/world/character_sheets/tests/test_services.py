"""Tests for character_sheets.services."""

from django.test import TestCase

from world.character_sheets.services import create_character_with_sheet


class CreateCharacterWithSheetTest(TestCase):
    def test_creates_all_three_objects(self) -> None:
        character, sheet, persona = create_character_with_sheet(
            character_key="TestPC",
            primary_persona_name="Bob",
        )
        assert character.pk == sheet.pk  # CharacterSheet uses primary_key on ObjectDB OneToOne
        assert persona.character_sheet_id == sheet.pk
        assert persona.name == "Bob"
        from world.scenes.constants import PersonaType

        assert persona.persona_type == PersonaType.PRIMARY

    def test_primary_persona_property_works(self) -> None:
        _, sheet, primary = create_character_with_sheet(
            character_key="TestPC2",
            primary_persona_name="Alice",
        )
        assert sheet.primary_persona == primary

    def test_atomic_rollback_on_failure(self) -> None:
        """If persona creation fails, character + sheet should NOT exist."""
        from world.character_sheets.models import CharacterSheet

        initial_count = CharacterSheet.objects.count()
        with self.assertRaises(TypeError):
            # Pass an invalid kwarg to force failure
            create_character_with_sheet(
                character_key="TestPC3",
                primary_persona_name="Charlie",
                nonexistent_field="should fail",
            )
        # Sheet count unchanged because the transaction rolled back
        assert CharacterSheet.objects.count() == initial_count
