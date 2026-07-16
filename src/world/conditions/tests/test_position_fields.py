"""Tests for cast-time position FK fields on ConditionInstance (#2019)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.areas.positioning.factories import PositionFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance


class ConditionInstancePositionFieldsTest(TestCase):
    """The three nullable Position FKs carry player-chosen position targets
    from the cast pipeline to effect handlers (#2019).
    """

    def setUp(self) -> None:
        self.target = ObjectDBFactory(db_key="test_char")
        self.template = ConditionTemplateFactory()
        self.pos = PositionFactory()

    def test_cast_destination_nullable_by_default(self) -> None:
        """New instances have null position FKs by default."""
        inst = ConditionInstance.objects.create(target=self.target, condition=self.template)
        self.assertIsNone(inst.cast_destination)
        self.assertIsNone(inst.cast_position_a)
        self.assertIsNone(inst.cast_position_b)

    def test_cast_destination_settable(self) -> None:
        """cast_destination can be set to a Position."""
        inst = ConditionInstance.objects.create(
            target=self.target, condition=self.template, cast_destination=self.pos
        )
        self.assertEqual(inst.cast_destination, self.pos)

    def test_cast_position_a_and_b_settable(self) -> None:
        """cast_position_a and cast_position_b can both be set."""
        pos2 = PositionFactory(room=self.pos.room)
        inst = ConditionInstance.objects.create(
            target=self.target,
            condition=self.template,
            cast_position_a=self.pos,
            cast_position_b=pos2,
        )
        self.assertEqual(inst.cast_position_a, self.pos)
        self.assertEqual(inst.cast_position_b, pos2)
