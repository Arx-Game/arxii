from django.test import TestCase

from world.traits.models import TraitType


class TraitTypeTests(TestCase):
    def test_modifier_type_exists(self):
        """TraitType should have MODIFIER option for contextual bonuses."""
        assert TraitType.MODIFIER == "modifier"
        assert TraitType.MODIFIER.label == "Modifier"
