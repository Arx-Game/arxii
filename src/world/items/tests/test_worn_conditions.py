"""Worn conditions: what the wearing journeys cannot reach (#5074).

The journeys (``integration_tests/test_wearing_magical_gear_journeys.py``) cover wearing,
taking off, dispels, mantle levels and the cost of a use. These cover staff authoring (the
admin refusals), the admin's save and delete hooks, and the hard delete of a worn item.
"""

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import has_condition
from world.items.admin import ItemInstanceAdmin, ItemWornConditionInline
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    ItemWornConditionFactory,
    MantleFactory,
    TemplateSlotFactory,
)
from world.items.models import ItemInstance, ItemWornCondition
from world.items.services.equip import equip_item
from world.items.services.usage import destroy_consumed_item_instance, hard_delete_item_instance
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

    def test_using_up_a_worn_item_takes_its_condition_off_the_wearer(self) -> None:
        self.wear()

        destroy_consumed_item_instance(self.ring, note="used up")

        self.assertFalse(has_condition(self.character, self.warding))

    def test_a_row_staff_save_in_the_item_admin_reaches_the_wearer(self) -> None:
        self.wear()
        other = _gear_condition("Keen Edge")
        request, model_admin = self.admin_request()
        formset_class = ItemWornConditionInline(ItemInstance, site).get_formset(request, self.ring)
        formset = formset_class(
            {
                "worn_conditions-TOTAL_FORMS": "1",
                "worn_conditions-INITIAL_FORMS": "0",
                "worn_conditions-MIN_NUM_FORMS": "0",
                "worn_conditions-MAX_NUM_FORMS": "1000",
                "worn_conditions-0-condition": str(other.pk),
                "worn_conditions-0-mantle_level": "",
            },
            instance=self.ring,
        )
        self.assertTrue(formset.is_valid(), formset.errors)

        model_admin.save_formset(
            request, model_admin.get_form(request, self.ring)(instance=self.ring), formset, True
        )

        self.assertTrue(has_condition(self.character, other))

    def test_a_staff_delete_of_a_worn_item_takes_its_condition_off_the_wearer(self) -> None:
        self.wear()
        request, model_admin = self.admin_request()

        model_admin.delete_model(request, self.ring)

        self.assertFalse(has_condition(self.character, self.warding))

    def test_another_worn_item_keeps_a_condition_the_deleted_one_also_gave(self) -> None:
        second_template = ItemTemplateFactory(name="Signet Hood")
        TemplateSlotFactory(
            template=second_template,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.BASE,
        )
        second_template.__dict__.pop("cached_slots", None)
        hood = ItemInstanceFactory(template=second_template)
        ItemWornConditionFactory(item_instance=hood, condition=self.warding)
        self.wear()
        equip_item(
            character_sheet=self.sheet,
            item_instance=hood,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.BASE,
        )

        hard_delete_item_instance(self.ring)

        instance = ConditionInstance.objects.get(target=self.character, condition=self.warding)
        self.assertEqual(instance.source_item, hood)

    def admin_request(self):
        request = RequestFactory().post("/")
        request.user = get_user_model().objects.create_superuser(
            "staff5074", "s5074@example.com", "pw-5074"
        )
        return request, ItemInstanceAdmin(ItemInstance, site)
