"""Tests for CharacterVitals life_state field and is_dead/is_alive services."""

from django.test import TestCase

from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import is_alive, is_dead


class LifeStateTests(TestCase):
    def test_defaults_alive(self) -> None:
        v = CharacterVitalsFactory()
        self.assertEqual(v.life_state, CharacterLifeState.ALIVE)
        self.assertTrue(is_alive(v.character_sheet.character))
        self.assertFalse(is_dead(v.character_sheet.character))

    def test_dead(self) -> None:
        v = CharacterVitalsFactory(life_state=CharacterLifeState.DEAD)
        self.assertTrue(is_dead(v.character_sheet.character))
        self.assertFalse(is_alive(v.character_sheet.character))
