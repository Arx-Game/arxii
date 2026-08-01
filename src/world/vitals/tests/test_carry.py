"""Carrying + robbing unconscious bodies (#2852). SQLite tier — consciousness
is patched at the ``can_act`` seam rather than applying PG-only conditions."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.carry_services import (
    CarryError,
    carried_body_follow,
    pick_up_body,
    set_down_body,
)
from world.vitals.models import CarriedBody


def _conscious_only(*sheets):
    """Patch can_act to be True only for the given sheets."""
    pks = {s.pk for s in sheets}
    return patch(
        "world.vitals.services.can_act",
        side_effect=lambda sheet: sheet is not None and sheet.pk in pks,
    )


class PickUpBodyTest(TestCase):
    def setUp(self):
        self.room = RoomProfileFactory().objectdb
        self.carrier_sheet = CharacterSheetFactory()
        self.carrier = self.carrier_sheet.character
        self.carrier.location = self.room
        self.target_sheet = CharacterSheetFactory()
        self.target = self.target_sheet.character
        self.target.location = self.room

    def test_carries_a_downed_colocated_body(self):
        with (
            _conscious_only(self.carrier_sheet),
            patch(
                "world.vitals.carry_services._consent_blocks_body_handling",
                return_value=False,
            ),
        ):
            link = pick_up_body(self.carrier, self.target)
        self.assertEqual(link.carrier, self.carrier_sheet)
        self.assertEqual(link.carried, self.target_sheet)

    def test_refuses_an_awake_target(self):
        with (
            _conscious_only(self.carrier_sheet, self.target_sheet),
            self.assertRaises(CarryError),
        ):
            pick_up_body(self.carrier, self.target)

    def test_consent_blocks_pc_bodies(self):
        with (
            _conscious_only(self.carrier_sheet),
            patch(
                "world.vitals.carry_services._consent_blocks_body_handling",
                return_value=True,
            ),
            self.assertRaises(CarryError) as caught,
        ):
            pick_up_body(self.carrier, self.target)
        self.assertIn("consent", str(caught.exception))

    def test_one_body_per_carrier(self):
        third_sheet = CharacterSheetFactory()
        third_sheet.character.location = self.room
        with (
            _conscious_only(self.carrier_sheet),
            patch(
                "world.vitals.carry_services._consent_blocks_body_handling",
                return_value=False,
            ),
        ):
            pick_up_body(self.carrier, self.target)
            with self.assertRaises(CarryError):
                pick_up_body(self.carrier, third_sheet.character)


class SetDownAndFollowTest(TestCase):
    def setUp(self):
        self.carrier_sheet = CharacterSheetFactory()
        self.carrier = self.carrier_sheet.character
        self.target_sheet = CharacterSheetFactory()
        self.target = self.target_sheet.character
        CarriedBody.objects.create(carrier=self.carrier_sheet, carried=self.target_sheet)

    def test_set_down_releases(self):
        set_down_body(self.carrier)
        self.assertFalse(CarriedBody.objects.exists())

    def test_set_down_without_a_body_refuses(self):
        set_down_body(self.carrier)
        with self.assertRaises(CarryError):
            set_down_body(self.carrier)

    def test_follow_brings_the_body_along(self):
        with _conscious_only(self.carrier_sheet):
            carried_body_follow(self.carrier)
        self.assertEqual(self.target.location, self.carrier.location)
        self.assertTrue(CarriedBody.objects.exists())

    def test_waking_ends_the_carry(self):
        with _conscious_only(self.carrier_sheet, self.target_sheet):
            carried_body_follow(self.carrier)
        self.assertFalse(CarriedBody.objects.exists())


class RobUnconsciousTest(TestCase):
    def test_unconscious_holder_items_become_steal_reachable(self):
        from flows.service_functions.inventory import _unconscious_holder_reachable
        from world.items.factories import ItemInstanceFactory

        room = RoomProfileFactory().objectdb
        thief_sheet = CharacterSheetFactory()
        thief = thief_sheet.character
        thief.location = room
        victim_sheet = CharacterSheetFactory()
        victim = victim_sheet.character
        victim.location = room
        from evennia import create_object

        obj = create_object("typeclasses.objects.Object", key="coin pouch", nohome=True)
        obj.location = victim
        instance = ItemInstanceFactory(holder_character_sheet=victim_sheet, game_object=obj)

        class _State:
            obj = thief

        class _ItemState:
            pass

        item_state = _ItemState()
        item_state.instance = instance
        with _conscious_only(thief_sheet):
            self.assertTrue(_unconscious_holder_reachable(_State(), item_state))
        with _conscious_only(thief_sheet, victim_sheet):
            self.assertFalse(_unconscious_holder_reachable(_State(), item_state))

    def test_worn_gear_stays_unreachable(self):
        from flows.service_functions.inventory import _unconscious_holder_reachable
        from world.items.factories import ItemInstanceFactory
        from world.items.models import EquippedItem

        room = RoomProfileFactory().objectdb
        thief_sheet = CharacterSheetFactory()
        thief = thief_sheet.character
        thief.location = room
        victim_sheet = CharacterSheetFactory()
        victim = victim_sheet.character
        victim.location = room
        from evennia import create_object

        obj = create_object("typeclasses.objects.Object", key="worn cloak", nohome=True)
        obj.location = victim
        instance = ItemInstanceFactory(holder_character_sheet=victim_sheet, game_object=obj)
        EquippedItem.objects.create(
            character=victim_sheet,
            item_instance=instance,
            body_region="torso",
            equipment_layer="base",
        )

        class _State:
            obj = thief

        class _ItemState:
            pass

        item_state = _ItemState()
        item_state.instance = instance
        with _conscious_only(thief_sheet):
            self.assertFalse(_unconscious_holder_reachable(_State(), item_state))
