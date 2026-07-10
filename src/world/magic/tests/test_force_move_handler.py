"""Tests for force_move_target_on_condition handler (#2019)."""

from types import SimpleNamespace

from django.test import TestCase

from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import place_in_position, position_of
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.services.effect_handlers import force_move_target_on_condition


class ForceMoveHandlerTest(TestCase):
    """force_move_target_on_condition force-moves + fires landing checks (#2019)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="test_room")
        self.target = create_object("typeclasses.characters.Character", key="enemy")
        self.target.db_location = self.room
        self.target.save()
        self.dest = PositionFactory(room=self.room, name="destination")
        self.start = PositionFactory(room=self.room, name="start")
        place_in_position(self.target, self.start)
        self.template = ConditionTemplateFactory()
        self.instance = ConditionInstance.objects.create(
            target=self.target,
            condition=self.template,
            cast_destination=self.dest,
        )

    def test_force_move_relocates_target(self) -> None:
        """The handler force-moves the target to the cast destination."""
        payload = SimpleNamespace(target=self.target, instance=self.instance)
        force_move_target_on_condition(payload=payload, destination_position_id=0)
        self.assertEqual(position_of(self.target), self.dest)

    def test_force_move_noop_when_no_destination(self) -> None:
        """When no destination is set, the handler is a no-op."""
        template2 = ConditionTemplateFactory()
        instance = ConditionInstance.objects.create(target=self.target, condition=template2)
        payload = SimpleNamespace(target=self.target, instance=instance)
        force_move_target_on_condition(payload=payload, destination_position_id=0)
        self.assertEqual(position_of(self.target), self.start)

    def test_force_move_noop_when_no_instance(self) -> None:
        """When payload has no instance, falls back to step param or no-op."""
        payload = SimpleNamespace(target=self.target)
        force_move_target_on_condition(payload=payload, destination_position_id=0)
        self.assertEqual(position_of(self.target), self.start)
