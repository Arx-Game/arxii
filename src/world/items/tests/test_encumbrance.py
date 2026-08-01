"""Encumbrance (#2862). SQLite tier."""

from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.encumbrance import (
    CARRIED_BODY_WEIGHT,
    EncumbranceBand,
    carried_load,
    carry_capacity,
    charge_move_fatigue,
    encumbrance_band,
    movement_blocked_message,
)


def _give(character, weight, key="sack"):
    obj = create_object("typeclasses.objects.Object", key=key, nohome=True)
    obj.location = character
    instance = ItemInstanceFactory(
        template=ItemTemplateFactory(weight=weight),
        holder_character_sheet=character.character_sheet,
        game_object=obj,
    )
    character.carried_items.invalidate()
    return instance


class EncumbranceBandTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_empty_hands_are_free(self):
        self.assertEqual(encumbrance_band(self.character), EncumbranceBand.FREE)

    def test_generous_capacity_scales_with_strength(self):
        base = carry_capacity(self.character)
        with patch.object(type(self.character.traits), "get_trait_value", return_value=50):
            strong = carry_capacity(self.character)
        self.assertGreater(strong, base)

    def test_worn_gear_is_free(self):
        from world.items.models import EquippedItem

        instance = _give(self.character, weight=10_000, key="worn plate")
        EquippedItem.objects.create(
            character=self.sheet,
            item_instance=instance,
            body_region="torso",
            equipment_layer="base",
        )
        self.assertEqual(carried_load(self.character), 0)

    def test_bands_progress_with_load(self):
        capacity = carry_capacity(self.character)
        _give(self.character, weight=capacity + 1)
        self.assertEqual(encumbrance_band(self.character), EncumbranceBand.ENCUMBERED)
        _give(self.character, weight=capacity * 2, key="anvil")
        self.assertEqual(encumbrance_band(self.character), EncumbranceBand.OVERLOADED)

    def test_carried_body_counts(self):
        from world.vitals.models import CarriedBody

        other = CharacterSheetFactory()
        CarriedBody.objects.create(carrier=self.sheet, carried=other)
        self.assertEqual(carried_load(self.character), CARRIED_BODY_WEIGHT)


class MoveCostTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_under_capacity_never_charges(self):
        """The ruled invariant: below the line, movement is free — always."""
        with patch("world.fatigue.services.apply_fatigue") as charge:
            charge_move_fatigue(self.character)
        charge.assert_not_called()

    def test_over_capacity_charges_and_says_so(self):
        capacity = carry_capacity(self.character)
        _give(self.character, weight=capacity + 1)
        with (
            patch("world.fatigue.services.apply_fatigue") as charge,
            patch.object(self.character, "msg") as msg,
        ):
            charge_move_fatigue(self.character)
        charge.assert_called_once()
        msg.assert_called_once()

    def test_block_needs_both_overload_and_exhaustion(self):
        from world.fatigue.constants import FatigueZone

        capacity = carry_capacity(self.character)
        _give(self.character, weight=capacity * 3)
        with patch(
            "world.fatigue.services.get_fatigue_zone",
            return_value=FatigueZone.FRESH,
        ):
            self.assertIsNone(movement_blocked_message(self.character))
        with patch(
            "world.fatigue.services.get_fatigue_zone",
            return_value=FatigueZone.EXHAUSTED,
        ):
            message = movement_blocked_message(self.character)
        self.assertIsNotNone(message)
        self.assertIn("Drop something", message)

    def test_merely_encumbered_never_blocks_even_exhausted(self):
        from world.fatigue.constants import FatigueZone

        capacity = carry_capacity(self.character)
        _give(self.character, weight=capacity + 1)
        with patch(
            "world.fatigue.services.get_fatigue_zone",
            return_value=FatigueZone.EXHAUSTED,
        ):
            self.assertIsNone(movement_blocked_message(self.character))
