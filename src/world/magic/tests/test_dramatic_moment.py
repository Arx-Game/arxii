from django.test import TestCase

from world.magic.factories import DramaticMomentTagFactory, DramaticMomentTypeFactory
from world.magic.models.dramatic_moment import DramaticMomentTag


class DramaticMomentTypeModelTest(TestCase):
    def test_create(self):
        dmt = DramaticMomentTypeFactory(label="Grand Entrance", resonance_amount=15)
        self.assertEqual(dmt.label, "Grand Entrance")
        self.assertEqual(dmt.resonance_amount, 15)
        self.assertIsNotNone(dmt.resonance_id)

    def test_str(self):
        dmt = DramaticMomentTypeFactory(label="Grand Entrance")
        self.assertEqual(str(dmt), "Grand Entrance")


class DramaticMomentTagModelTest(TestCase):
    def test_create(self):
        tag = DramaticMomentTagFactory()
        self.assertIsInstance(tag, DramaticMomentTag)
        self.assertIsNotNone(tag.moment_type_id)
        self.assertIsNotNone(tag.character_sheet_id)
        self.assertIsNotNone(tag.tagged_by_id)
        self.assertIsNotNone(tag.tagged_at)

    def test_str(self):
        tag = DramaticMomentTagFactory()
        self.assertIn("DramaticMomentTag", str(tag))
