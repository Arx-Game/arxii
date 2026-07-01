"""Tests for the TechniqueGrant sidecar model (#1732)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.items.factories import ItemTemplateFactory
from world.magic.factories import RitualFactory, TechniqueFactory
from world.magic.models import TechniqueGrant


class TechniqueGrantModelTest(TestCase):
    def setUp(self):
        self.technique = TechniqueFactory()
        self.item_template = ItemTemplateFactory()
        self.ritual = RitualFactory()

    def test_item_grant_clean(self):
        """A grant with item_template set and ritual null is valid."""
        grant = TechniqueGrant(
            technique=self.technique,
            item_template=self.item_template,
        )
        grant.clean()  # should not raise

    def test_ritual_grant_clean(self):
        """A grant with ritual set and item_template null is valid."""
        grant = TechniqueGrant(
            technique=self.technique,
            ritual=self.ritual,
        )
        grant.clean()  # should not raise

    def test_neither_vehicle_raises(self):
        """A grant with neither item_template nor ritual is invalid."""
        grant = TechniqueGrant(technique=self.technique)
        with self.assertRaises(ValidationError):
            grant.clean()

    def test_both_vehicles_raises(self):
        """A grant with both item_template and ritual is invalid."""
        grant = TechniqueGrant(
            technique=self.technique,
            item_template=self.item_template,
            ritual=self.ritual,
        )
        with self.assertRaises(ValidationError):
            grant.clean()

    def test_str(self):
        grant = TechniqueGrant(
            technique=self.technique,
            item_template=self.item_template,
            verb="study",
        )
        self.assertIn(self.technique.name, str(grant))
