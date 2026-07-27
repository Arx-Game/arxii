"""Species aging fields (#2756): eternal_youth + decline_start_age."""

from django.test import TestCase

from world.species.factories import SpeciesFactory


class SpeciesAgingFieldTests(TestCase):
    def test_defaults_mortal_decline_at_sixty(self):
        species = SpeciesFactory(name="Mortalkind")
        self.assertFalse(species.eternal_youth)
        self.assertEqual(species.decline_start_age, 60)

    def test_eternal_youth_species_never_declines(self):
        species = SpeciesFactory(
            name="Rex'alfar (test)", eternal_youth=True, decline_start_age=None
        )
        self.assertTrue(species.eternal_youth)
        self.assertIsNone(species.decline_start_age)
