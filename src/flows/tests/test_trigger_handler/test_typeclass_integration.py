from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.trigger_handler import TriggerHandler


class TypeclassHandlerAccessTests(TestCase):
    def test_character_has_trigger_handler(self) -> None:
        char = CharacterFactory()
        self.assertIsInstance(char.trigger_handler, TriggerHandler)
        self.assertIs(char.trigger_handler.owner, char)

    def test_handler_is_cached(self) -> None:
        char = CharacterFactory()
        self.assertIs(char.trigger_handler, char.trigger_handler)
