from django.test import TestCase

from world.magic.factories import TechniqueFactory
from world.mechanics.factories import PrerequisiteFactory


class ComboOpeningProbingFieldTest(TestCase):
    def test_defaults_to_none(self):
        tech = TechniqueFactory()
        self.assertIsNone(tech.combo_opening_probing)

    def test_accepts_positive_value(self):
        tech = TechniqueFactory(combo_opening_probing=3)
        tech.refresh_from_db()
        self.assertEqual(tech.combo_opening_probing, 3)


class TechniqueTargetPrerequisitesTest(TestCase):
    def test_target_prerequisites_m2m_and_cache(self) -> None:
        technique = TechniqueFactory(damage_profile=False)
        prereq = PrerequisiteFactory()
        technique.target_prerequisites.add(prereq)

        self.assertIn(prereq, technique.target_prerequisites.all())
        self.assertEqual(technique.cached_target_prerequisites, [prereq])

    def test_cached_target_prerequisites_empty_by_default(self) -> None:
        technique = TechniqueFactory(damage_profile=False)
        self.assertEqual(technique.cached_target_prerequisites, [])
