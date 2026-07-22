"""Pure-function unit tests for vow_keyed_diminished_total (#2643).

Vow-keyed diminishing returns for the bounded team-damage-percent lane:
contributions sharing one vow key diminish 100/50/25/25...%; distinct vow keys
(including the ``None`` "no engaged role" key) stack fully against each other.
"""

from django.test import SimpleTestCase

from world.magic.services.techniques import vow_keyed_diminished_total


class VowKeyedDiminishedTotalTests(SimpleTestCase):
    def test_empty_input_is_zero(self):
        self.assertEqual(vow_keyed_diminished_total({}), 0)

    def test_single_contribution_is_unweighted(self):
        self.assertEqual(vow_keyed_diminished_total({1: [20]}), 20)

    def test_two_same_vow_sources_weight_full_and_half(self):
        # 20*1.0 + 20*0.5 = 30
        self.assertEqual(vow_keyed_diminished_total({1: [20, 20]}), 30)

    def test_third_same_vow_source_weights_quarter(self):
        # 20*1.0 + 20*0.5 + 20*0.25 = 35
        self.assertEqual(vow_keyed_diminished_total({1: [20, 20, 20]}), 35)

    def test_fourth_and_beyond_same_vow_source_also_weights_quarter(self):
        # 20*1.0 + 20*0.5 + 20*0.25 + 20*0.25 = 40 (no further decay past the 3rd)
        self.assertEqual(vow_keyed_diminished_total({1: [20, 20, 20, 20]}), 40)

    def test_descending_order_applies_regardless_of_input_order(self):
        # Weights always land on the LARGEST contribution first, regardless of
        # the order they appear in the input list: sorted descending [30, 20, 10].
        # 30*1.0 + 20*0.5 + 10*0.25 = 30 + 10 + 2.5 = 42.5 -> ROUND_HALF_UP -> 43
        self.assertEqual(vow_keyed_diminished_total({1: [10, 30, 20]}), 43)

    def test_two_different_vows_stack_fully(self):
        # Each vow's own group gets full weight on its single contribution:
        # 20 (vow 1) + 20 (vow 2) = 40, no diminishing across groups.
        self.assertEqual(vow_keyed_diminished_total({1: [20], 2: [20]}), 40)

    def test_none_vow_key_is_its_own_group(self):
        # A None-keyed (no engaged role) contribution stacks fully against a
        # named-vow contribution — it is just another distinct group.
        self.assertEqual(vow_keyed_diminished_total({None: [20], 1: [20]}), 40)

    def test_mixed_groups_diminish_within_and_stack_across(self):
        # Vow 1: 20*1.0 + 20*0.5 = 30. Vow 2: 20 (single, full). Total 50.
        self.assertEqual(vow_keyed_diminished_total({1: [20, 20], 2: [20]}), 50)

    def test_negative_contributions_supported(self):
        # A debuff (Undermine, negative delta) diminishes the same way.
        self.assertEqual(vow_keyed_diminished_total({1: [-20, -20]}), -30)
