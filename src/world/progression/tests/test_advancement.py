"""Model-shape tests for ClassLevelAdvancement receipt (#1352)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.progression.models import ClassLevelAdvancement
from world.progression.services.advancement import apply_class_level_advance, primary_class_level


class ClassLevelAdvancementModelTests(TestCase):
    def test_fields_and_str(self):
        fields = {f.name for f in ClassLevelAdvancement._meta.get_fields()}
        assert {
            "character_sheet",
            "character_class",
            "officiant",
            "ritual",
            "scene",
            "declaration_interaction",
            "level_before",
            "level_after",
            "created_at",
        } <= fields


class ApplyClassLevelAdvanceTests(TestCase):
    """apply_class_level_advance bumps the primary CharacterClassLevel and invalidates cache."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ccl = CharacterClassLevelFactory(
            character=self.sheet.character,
            level=2,
            is_primary=True,
        )

    def test_bumps_primary_class_level_to_level_after(self) -> None:
        apply_class_level_advance(self.sheet, level_after=3)
        self.ccl.refresh_from_db()
        assert self.ccl.level == 3

    def test_cache_invalidated_so_current_level_reflects_new_level(self) -> None:
        apply_class_level_advance(self.sheet, level_after=3)
        assert self.sheet.current_level == 3

    def test_noop_when_no_class_level_row_exists(self) -> None:
        """apply_class_level_advance silently does nothing when there is no CharacterClassLevel."""
        from world.classes.models import CharacterClassLevel

        sheet = CharacterSheetFactory()
        assert not CharacterClassLevel.objects.filter(character=sheet.character).exists()
        # Must not raise.
        apply_class_level_advance(sheet, level_after=3)


class PrimaryClassLevelTests(TestCase):
    """primary_class_level returns the primary row, falls back to highest-level, else None."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def test_returns_primary_row_when_present(self) -> None:
        CharacterClassLevelFactory(character=self.sheet.character, level=10, is_primary=False)
        ccl_primary = CharacterClassLevelFactory(
            character=self.sheet.character, level=1, is_primary=True
        )
        result = primary_class_level(self.sheet.character)
        assert result == ccl_primary

    def test_falls_back_to_highest_level_when_no_primary(self) -> None:
        CharacterClassLevelFactory(character=self.sheet.character, level=3, is_primary=False)
        ccl_high = CharacterClassLevelFactory(
            character=self.sheet.character, level=7, is_primary=False
        )
        result = primary_class_level(self.sheet.character)
        assert result == ccl_high

    def test_returns_none_when_no_rows(self) -> None:
        result = primary_class_level(self.sheet.character)
        assert result is None
