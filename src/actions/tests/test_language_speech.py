"""Listener comprehension is one batched read per say, not one per listener (#4090).

The speech itself is a journey (``integration_tests/test_voice_and_feeling_journeys.py``);
a query count is not something a typed line shows.
"""

import traceback

from django.db import connection
from django.test import TestCase

from actions.definitions.communication import SayAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory
from world.mechanics.models import ModifierTarget
from world.species import language_services
from world.species.factories import make_language_with_target, make_understanding_condition
from world.species.language_services import comprehension_values
from world.traits.models import CharacterTraitValue


def _make_room():
    return ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")


class ComprehensionQueryCountTests(TestCase):
    """#4090: listener comprehension is one batched read per say, not one per listener."""

    TEXT = "the ferry waits at the low quay until the tide turns"

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        CharacterTraitValue.flush_instance_cache()
        self.language, self.target = make_language_with_target("QueryCountTongue")
        self.condition = make_understanding_condition(
            "Placeholder Query Understanding", self.target
        )

    def _room_with_listeners(self, count: int):
        room = _make_room()
        speaker = CharacterFactory(db_key="Envoy", location=room)
        speaker_sheet = CharacterSheetFactory(character=speaker)
        CharacterTraitValue.objects.create(
            character=speaker_sheet, trait=self.language.trait, value=100
        )
        sheets = []
        for index in range(count):
            listener = CharacterFactory(db_key=f"Listener{index}", location=room)
            sheets.append(CharacterSheetFactory(character=listener))
            CharacterTraitValue.objects.create(
                character=sheets[-1], trait=self.language.trait, value=10
            )
            ConditionInstanceFactory(target=listener, condition=self.condition, severity=4)
        return speaker, sheets

    def _comprehension_queries_for_say(self, listener_count: int) -> int:
        """Queries issued from inside language_services during one say (both live paths).

        Other per-recipient reads (object-state construction resolves condition
        thumbnails per recipient) are outside comprehension, so they are not counted.
        """
        speaker, _sheets = self._room_with_listeners(listener_count)
        # Warm the one-time caches (the language's trait FK, get_for_trait's map).
        ModifierTarget.get_for_trait(self.language.trait)
        services_file = language_services.__file__
        counted: list[str] = []

        def _count_comprehension(execute, sql, params, many, context):
            if any(frame.filename == services_file for frame in traceback.extract_stack()):
                counted.append(sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(_count_comprehension):
            result = SayAction().run(speaker, text=self.TEXT, language_id=self.language.pk)
        assert result.success is True
        return len(counted)

    def test_say_to_one_or_four_listeners_costs_the_same_comprehension_queries(self) -> None:
        """Covers both live paths: telnet per-recipient delivery and the web push."""
        one = self._comprehension_queries_for_say(1)
        four = self._comprehension_queries_for_say(4)
        assert one > 0
        assert one == four, (one, four)

    def test_comprehension_values_is_constant_in_sheet_count(self) -> None:
        _speaker, one_sheet = self._room_with_listeners(1)
        _speaker, four_sheets = self._room_with_listeners(4)
        self.language.trait  # noqa: B018 - warm the FK so only the batched reads are counted
        ModifierTarget.get_for_trait(self.language.trait)
        with self.assertNumQueries(3):
            one = comprehension_values([one_sheet[0].pk], self.language)
        with self.assertNumQueries(3):
            four = comprehension_values([sheet.pk for sheet in four_sheets], self.language)
        assert one == {one_sheet[0].pk: 90}
        assert four == {sheet.pk: 90 for sheet in four_sheets}
