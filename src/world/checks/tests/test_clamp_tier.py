"""clamp_tier_to_pool (#3559): a roll above every authored tier fires the best authored tier."""

from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.consequence_resolution import clamp_tier_to_pool
from world.checks.factories import ConsequenceFactory
from world.traits.factories import CheckOutcomeFactory


class ClampTierTests(EvenniaTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.win3 = CheckOutcomeFactory(name="Win 3", success_level=3)
        cls.win6 = CheckOutcomeFactory(name="Win 6", success_level=6)
        cls.lose2 = CheckOutcomeFactory(name="Lose 2", success_level=-2)
        cls.pool = ConsequencePoolFactory()
        for tier in (cls.win3, cls.win6, cls.lose2):
            ConsequencePoolEntryFactory(
                pool=cls.pool, consequence=ConsequenceFactory(outcome_tier=tier)
            )

    def test_exact_match_returns_itself(self) -> None:
        assert clamp_tier_to_pool(self.pool, self.win6) == self.win6

    def test_above_every_authored_tier_clamps_to_best(self) -> None:
        nine = CheckOutcomeFactory(name="Win 9", success_level=9)
        assert clamp_tier_to_pool(self.pool, nine) == self.win6

    def test_between_tiers_clamps_down_not_up(self) -> None:
        five = CheckOutcomeFactory(name="Win 5", success_level=5)
        assert clamp_tier_to_pool(self.pool, five) == self.win3

    def test_failure_polarity_clamps_toward_zero(self) -> None:
        six_down = CheckOutcomeFactory(name="Lose 6", success_level=-6)
        assert clamp_tier_to_pool(self.pool, six_down) == self.lose2

    def test_no_row_of_that_polarity_returns_none(self) -> None:
        win_only = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(
            pool=win_only, consequence=ConsequenceFactory(outcome_tier=self.win3)
        )
        assert clamp_tier_to_pool(win_only, self.lose2) is None
