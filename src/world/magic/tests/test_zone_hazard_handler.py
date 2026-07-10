"""Tests for create_zone_hazard_on_condition handler (#2019)."""

from types import SimpleNamespace

from django.test import TestCase

from world.areas.positioning.factories import PositionFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.services.effect_handlers import create_zone_hazard_on_condition


class ZoneHazardHandlerTest(TestCase):
    """create_zone_hazard_on_condition creates a Trap at the destination (#2019)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="hazard_room")
        self.dest = PositionFactory(room=self.room, name="center")
        self.sheet = CharacterSheetFactory()
        self.template = ConditionTemplateFactory()
        self.instance = ConditionInstance.objects.create(
            target=self.room,
            condition=self.template,
            cast_destination=self.dest,
            source_character=None,
        )
        from actions.factories import ConsequencePoolFactory
        from world.checks.factories import CheckTypeFactory

        self.pool = ConsequencePoolFactory()
        self.check = CheckTypeFactory()

    def test_zone_hazard_created_at_destination(self) -> None:
        """A Trap is created at the cast destination with duration + owner."""
        from world.room_features.models import Trap

        payload = SimpleNamespace(target=self.room, instance=self.instance)
        create_zone_hazard_on_condition(
            payload=payload,
            position_id=0,
            duration_rounds=3,
            consequence_pool_id=self.pool.pk,
            detect_check_type_id=self.check.pk,
        )
        hazard = Trap.objects.get(position=self.dest)
        self.assertTrue(hazard.is_armed)
        self.assertEqual(hazard.duration_rounds, 3)

    def test_zone_hazard_noop_without_destination(self) -> None:
        """When no destination is set, the handler is a no-op."""
        from world.room_features.models import Trap

        template2 = ConditionTemplateFactory()
        instance = ConditionInstance.objects.create(target=self.room, condition=template2)
        payload = SimpleNamespace(target=self.room, instance=instance)
        create_zone_hazard_on_condition(
            payload=payload,
            position_id=0,
            duration_rounds=3,
            consequence_pool_id=self.pool.pk,
            detect_check_type_id=self.check.pk,
        )
        self.assertEqual(Trap.objects.filter(position=self.dest).count(), 0)
