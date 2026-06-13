from django.test import TestCase

from world.magic.factories import TechniqueDamageProfileFactory


class UsesEquippedWeaponFlagTests(TestCase):
    def test_default_false(self):
        profile = TechniqueDamageProfileFactory()
        self.assertFalse(profile.uses_equipped_weapon)

    def test_can_opt_in(self):
        profile = TechniqueDamageProfileFactory(uses_equipped_weapon=True)
        self.assertTrue(profile.uses_equipped_weapon)
