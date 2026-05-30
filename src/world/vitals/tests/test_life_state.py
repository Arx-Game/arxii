"""Tests for CharacterVitals life_state field and is_dead/is_alive services."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import is_alive, is_dead


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
