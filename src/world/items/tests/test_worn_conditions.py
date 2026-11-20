"""Worn conditions: what the wearing journeys cannot reach (#5074).

The journeys (``integration_tests/test_wearing_magical_gear_journeys.py``) cover wearing,
taking off, dispels, mantle levels and the cost of a use. These cover staff authoring (the
admin refusals), the hard delete of a worn item, and a staff edit reaching the wearer.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import has_condition
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    ItemWornConditionFactory,
    MantleFactory,
    TemplateSlotFactory,
)
from world.items.models import ItemWornCondition
from world.items.services.equip import equip_item
from world.items.services.usage import hard_delete_item_instance
from world.items.services.worn_conditions import reconcile_item_wearers
from world.magic.factories import TechniqueAppliedConditionFactory


def _gear_condition(name: str):
    return ConditionTemplateFactory(name=name, default_duration_type=DurationType.PERMANENT)


class StaffAuthoringTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.item = ItemInstanceFactory()
        cls.condition = _gear_condition("Warding")

    def test_a_mantle_level_on_a_plain_item_is_refused(self) -> None:
        row = ItemWornCondition(item_instance=self.item, condition=self.condition, mantle_level=1)

        with self.assertRaises(ValidationError) as caught:
            row.clean()

        self.assertIn("mantle_level", caught.exception.message_dict)

    def test_a_mantle_level_past_the_mantles_levels_is_refused(self) -> None:
        mantle = MantleFactory(max_level=2)
        row = ItemWornCondition(
            item_instance=mantle.item_instance, condition=self.condition, mantle_level=3
        )

        with self.assertRaises(ValidationError) as caught:
            row.clean()

        self.assertIn("mantle_level", caught.exception.message_dict)

    def test_a_mantle_level_within_the_mantles_levels_is_accepted(self) -> None:
        mantle = MantleFactory(max_level=3)

        ItemWornCondition(
            item_instance=mantle.item_instance, condition=self.condition, mantle_level=3
        ).clean()

    def test_an_item_cannot_give_a_condition_a_technique_applies(self) -> None:
        TechniqueAppliedConditionFactory(condition=self.condition)
        row = ItemWornCondition(item_instance=self.item, condition=self.condition)

        with self.assertRaises(ValidationError) as caught:
            row.clean()

        self.assertIn("condition", caught.exception.message_dict)

    def test_a_technique_cannot_apply_a_condition_an_item_gives(self) -> None:
        ItemWornConditionFactory(item_instance=self.item, condition=self.condition)
        row = TechniqueAppliedConditionFactory.build(condition=self.condition)

        with self.assertRaises(ValidationError) as caught:
            row.clean()

        self.assertIn("condition", caught.exception.message_dict)


class WornItemTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory(character=CharacterFactory())
        self.character = self.sheet.character
        template = ItemTemplateFactory(name="Signet Ring")
        TemplateSlotFactory(
            template=template, body_region=BodyRegion.TORSO, equipment_layer=EquipmentLayer.BASE
        )
        template.__dict__.pop("cached_slots", None)
        self.ring = ItemInstanceFactory(template=template)
        self.warding = _gear_condition("Warding")
        ItemWornConditionFactory(item_instance=self.ring, condition=self.warding)

    def wear(self) -> None:
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.ring,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def test_hard_deleting_a_worn_item_takes_its_condition_off_the_wearer(self) -> None:
        self.wear()
        self.assertTrue(has_condition(self.character, self.warding))

        hard_delete_item_instance(self.ring)

        self.assertFalse(has_condition(self.character, self.warding))
        self.assertFalse(ConditionInstance.objects.filter(target=self.character).exists())

    def test_a_row_staff_add_to_a_worn_item_reaches_the_wearer(self) -> None:
        self.wear()
        other = _gear_condition("Keen Edge")
        row = ItemWornConditionFactory(item_instance=self.ring, condition=other)

        reconcile_item_wearers(self.ring, apply_rows=[row])

        self.assertTrue(has_condition(self.character, other))

    def test_a_row_staff_delete_from_a_worn_item_leaves_the_wearer(self) -> None:
        self.wear()
        ItemWornCondition.objects.get(item_instance=self.ring, condition=self.warding).delete()

        reconcile_item_wearers(self.ring)

        self.assertFalse(has_condition(self.character, self.warding))
