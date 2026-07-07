"""Tests for regional house aspects + features (#2079)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.societies.houses.models import (
    HouseAspectDefinition,
    HouseAspectOption,
    HouseFeature,
)


class AspectModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.definition = HouseAspectDefinition.objects.create(
            name="House Virtue TEST",
            prompt="Which virtue did your house cling to?",
        )
        cls.option = HouseAspectOption.objects.create(
            definition=cls.definition, name="Fortitude TEST"
        )
        cls.feature = HouseFeature.objects.create(
            name="Hearth Right TEST",
            slug="hearth-right-test",
            description="Guests under your roof are sacrosanct.",
        )

    def test_definition_defaults_single_pick(self):
        self.assertEqual(self.definition.min_picks, 1)
        self.assertEqual(self.definition.max_picks, 1)

    def test_option_unique_per_definition(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            HouseAspectOption.objects.create(definition=self.definition, name="Fortitude TEST")

    def test_feature_slug_unique(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            HouseFeature.objects.create(
                name="Other TEST", slug="hearth-right-test", description="x"
            )
