from django.test import TestCase

from world.magic.constants import SoulTetherRole
from world.relationships.factories import CharacterRelationshipFactory


class SoulTetherFieldRoundTripTests(TestCase):
    def test_is_soul_tether_default_false(self):
        rel = CharacterRelationshipFactory()
        self.assertFalse(rel.is_soul_tether)

    def test_set_soul_tether_role_abyssal(self):
        rel = CharacterRelationshipFactory(
            is_soul_tether=True,
            soul_tether_role=SoulTetherRole.ABYSSAL,
            magical_flavor="the weight of debts owed",
        )
        rel.refresh_from_db()
        self.assertTrue(rel.is_soul_tether)
        self.assertEqual(rel.soul_tether_role, SoulTetherRole.ABYSSAL)
        self.assertEqual(rel.magical_flavor, "the weight of debts owed")
