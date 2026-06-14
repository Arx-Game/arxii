from django.db import IntegrityError, transaction
from django.test import TestCase

from world.items.factories import (
    ItemInstanceFactory,
    MantleFactory,
    MantleLevelClearanceFactory,
    MantleLevelDefinitionFactory,
)
from world.items.models import (
    Mantle,
    MantleLevelClearance,
    MantleLevelDefinition,
)


class MantleModelTests(TestCase):
    def test_mantle_one_to_one_with_item_instance(self):
        mantle = MantleFactory()
        self.assertEqual(mantle.item_instance.mantle, mantle)

    def test_one_item_instance_cannot_back_two_mantles(self):
        mantle = MantleFactory()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Mantle.objects.create(
                    item_instance=mantle.item_instance,
                    name="Second Mantle Same Item",
                )

    def test_mantle_name_unique(self):
        MantleFactory(name="The Bleeding Banner")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Mantle.objects.create(
                    item_instance=ItemInstanceFactory(),
                    name="The Bleeding Banner",
                )

    def test_max_level_zero_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Mantle.objects.create(
                    item_instance=ItemInstanceFactory(),
                    name="Zero Level Mantle",
                    max_level=0,
                )

    def test_max_level_eleven_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Mantle.objects.create(
                    item_instance=ItemInstanceFactory(),
                    name="Over Level Mantle",
                    max_level=11,
                )

    def test_max_level_default_is_five(self):
        mantle = Mantle.objects.create(
            item_instance=ItemInstanceFactory(),
            name="Default Level Mantle",
        )
        self.assertEqual(mantle.max_level, 5)


class MantleLevelDefinitionModelTests(TestCase):
    def test_level_definition_links_to_mantle(self):
        level_def = MantleLevelDefinitionFactory()
        self.assertIn(level_def, level_def.mantle.level_defs.all())

    def test_level_definition_unique_per_mantle_level(self):
        level_def = MantleLevelDefinitionFactory(level=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MantleLevelDefinition.objects.create(
                    mantle=level_def.mantle,
                    level=1,
                    codex_entry_required=level_def.codex_entry_required,
                )

    def test_same_level_across_mantles_allowed(self):
        first = MantleLevelDefinitionFactory(level=2)
        second = MantleLevelDefinitionFactory(level=2)
        self.assertNotEqual(first.mantle_id, second.mantle_id)


class MantleLevelClearanceModelTests(TestCase):
    def test_clearance_links_character_and_mantle(self):
        clearance = MantleLevelClearanceFactory()
        self.assertIn(clearance, clearance.character_sheet.mantle_clearances.all())
        self.assertIn(clearance, clearance.mantle.clearances.all())

    def test_clearance_unique_per_character_mantle_level(self):
        clearance = MantleLevelClearanceFactory(level=1)
        # Bypass the factory's django_get_or_create to force an insert that
        # collides with the unique constraint.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MantleLevelClearance.objects.create(
                    character_sheet=clearance.character_sheet,
                    mantle=clearance.mantle,
                    level=1,
                )
