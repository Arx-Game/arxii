from django.test import TestCase

from world.magic.factories import TechniqueFactory


class ComboOpeningProbingFieldTest(TestCase):
    def test_defaults_to_none(self):
        tech = TechniqueFactory()
        self.assertIsNone(tech.combo_opening_probing)

    def test_accepts_positive_value(self):
        tech = TechniqueFactory(combo_opening_probing=3)
        tech.refresh_from_db()
        self.assertEqual(tech.combo_opening_probing, 3)
