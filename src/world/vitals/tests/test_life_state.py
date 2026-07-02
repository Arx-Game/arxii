"""Tests for CharacterVitals life_state field and is_dead/is_alive services."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.types import LifecycleState
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import _mark_dead, is_alive, is_dead


class LifeStateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.alive_vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)

    def test_defaults_alive(self) -> None:
        v = self.alive_vitals
        self.assertEqual(v.life_state, CharacterLifeState.ALIVE)
        self.assertTrue(is_alive(v.character_sheet.character.sheet_data))
        self.assertFalse(is_dead(v.character_sheet.character.sheet_data))

    def test_dead(self) -> None:
        v = CharacterVitalsFactory(life_state=CharacterLifeState.DEAD)
        self.assertTrue(is_dead(v.character_sheet.character.sheet_data))
        self.assertFalse(is_alive(v.character_sheet.character.sheet_data))

    def test_no_vitals_is_alive(self) -> None:
        """Character with no CharacterSheet at all is considered alive by default.

        The post-OBJECTDB_PARAM refactor takes CharacterSheet | None; passing
        None covers the "ObjectDB has no sheet" path (NPCs without vitals
        tracking, fresh test fixtures, etc.).
        """
        CharacterFactory(db_key="no_vitals_life_state")
        self.assertTrue(is_alive(None))
        self.assertFalse(is_dead(None))

    def test_mark_dead_propagates_to_roster_lifecycle(self) -> None:
        """#1770 PR2: the single death writer also stamps CharacterSheet.lifecycle_state.

        Combat death (debited health -> process_damage_consequences -> terminal
        peril -> _mark_dead) must reach the roster lifecycle, so downstream
        systems (dormancy, stake grading) see the death without reading vitals.
        """
        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)
        sheet = vitals.character_sheet
        self.assertEqual(sheet.lifecycle_state, LifecycleState.ALIVE)

        _mark_dead(sheet)

        self.assertEqual(vitals.life_state, CharacterLifeState.DEAD)
        self.assertIsNotNone(vitals.died_at)
        sheet.refresh_from_db()
        self.assertEqual(sheet.lifecycle_state, LifecycleState.DEAD)
        self.assertIsNotNone(sheet.lifecycle_state_at)

    def test_mark_dead_without_vitals_is_noop(self) -> None:
        """No vitals row: _mark_dead returns early and never touches lifecycle."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        _mark_dead(sheet)
        sheet.refresh_from_db()
        self.assertEqual(sheet.lifecycle_state, LifecycleState.ALIVE)
