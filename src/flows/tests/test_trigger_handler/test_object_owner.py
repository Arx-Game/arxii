"""Verify non-Character ObjectDB instances (items, rooms) own triggers.

`trigger_handler` is exposed on `ObjectParent`, which Characters, Rooms,
Objects, and Exits all inherit. This test pins the contract: an item
sitting in a room (not held by a character) still populates its own
trigger handler from `Trigger` rows whose `obj` points at the item.
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.constants import EventName
from flows.trigger_handler import TriggerHandler
from world.conditions.factories import ReactiveConditionFactory


class ObjectOwnerTests(TestCase):
    def test_plain_object_has_trigger_handler(self) -> None:
        item = ObjectDBFactory()
        self.assertIsInstance(item.trigger_handler, TriggerHandler)
        self.assertIs(item.trigger_handler.owner, item)

    def test_item_trigger_populates_from_db(self) -> None:
        item = ObjectDBFactory()
        trigger = ReactiveConditionFactory(
            event_name=EventName.EXAMINED,
            target=item,
        )
        fetched = item.trigger_handler.triggers_for(EventName.EXAMINED)
        self.assertIn(trigger, fetched)

    def test_item_handler_cached(self) -> None:
        item = ObjectDBFactory()
        self.assertIs(item.trigger_handler, item.trigger_handler)
