"""change_supported guard + benefit-direction XP cost (#2607)."""

from django.test import TestCase

from world.distinctions.factories import DistinctionFactory
from world.distinctions.services import change_supported, distinction_change_xp_cost


class ChangeSupportedTests(TestCase):
    def test_plain_distinction_supported(self) -> None:
        assert change_supported(DistinctionFactory(post_cg_immutable=False)) is True

    def test_denylisted_unsupported(self) -> None:
        assert change_supported(DistinctionFactory(post_cg_immutable=True)) is False


class XpCostTests(TestCase):
    def test_gain_positive_costs(self) -> None:
        distinction = DistinctionFactory(cost_per_rank=4)
        assert distinction_change_xp_cost(distinction, rank=2, removing=False) == 24  # 3*|4*2|

    def test_remove_negative_costs(self) -> None:
        distinction = DistinctionFactory(cost_per_rank=-50)
        assert distinction_change_xp_cost(distinction, rank=1, removing=True) == 150

    def test_gain_negative_free(self) -> None:
        distinction = DistinctionFactory(cost_per_rank=-50)
        assert distinction_change_xp_cost(distinction, rank=1, removing=False) == 0

    def test_remove_positive_free(self) -> None:
        distinction = DistinctionFactory(cost_per_rank=4)
        assert distinction_change_xp_cost(distinction, rank=1, removing=True) == 0
