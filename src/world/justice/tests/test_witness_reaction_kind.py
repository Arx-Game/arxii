from django.test import TestCase

from world.scenes.constants import ReactionWindowKind


class WitnessKindConstantTests(TestCase):
    def test_witness_kind_exists(self) -> None:
        self.assertEqual(ReactionWindowKind.WITNESS, "witness")
