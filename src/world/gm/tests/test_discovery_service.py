"""find_situations: one search behind telnet and the web (#3564)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.gm.constants import GM_LEVEL_ORDER, GMLevel
from world.gm.factories import (
    CheckTypeSituationFitFactory,
    ConsequencePoolGuideFactory,
    GMProfileFactory,
    SituationDifficultyGuideFactory,
    SituationKindFactory,
)
from world.gm.services import find_situations, user_breadth_index
from world.mechanics.factories import ChallengeTemplateFactory, SituationTemplateFactory
from world.scenes.action_constants import DifficultyChoice
from world.societies.constants import RenownRisk

TOP = len(GM_LEVEL_ORDER) - 1


class FindSituationsTests(TestCase):
    def setUp(self) -> None:
        self.chase = SituationKindFactory(name="Chase", minimum_gm_level=GMLevel.STARTING)
        self.heist = SituationKindFactory(name="Heist", minimum_gm_level=GMLevel.SENIOR)
        self.sprint = CheckTypeFactory(name="Sprint")
        self.fit = CheckTypeSituationFitFactory(
            situation_kind=self.chase, check_type=self.sprint, fit_notes="footspeed"
        )
        self.low = SituationDifficultyGuideFactory(
            situation_kind=self.chase,
            risk=RenownRisk.LOW,
            recommended_difficulty=DifficultyChoice.EASY,
        )
        self.high = SituationDifficultyGuideFactory(
            situation_kind=self.chase,
            risk=RenownRisk.HIGH,
            recommended_difficulty=DifficultyChoice.HARD,
        )
        self.pool_guide = ConsequencePoolGuideFactory(situation_kind=self.chase, is_default=True)
        self.template = SituationTemplateFactory(name="Rooftop chase")
        self.challenge = ChallengeTemplateFactory(name="Chase the courier")

    def test_empty_query_returns_in_breadth_kinds_only(self) -> None:
        result = find_situations(query="", risk=None, actor_level_index=0)
        self.assertEqual(result.templates, [])
        self.assertEqual(result.challenges, [])
        self.assertEqual([k.kind for k in result.kinds], [self.chase])

    def test_query_matches_templates_challenges_and_kinds(self) -> None:
        result = find_situations(query="chase", risk=None, actor_level_index=0)
        self.assertEqual(result.templates, [self.template])
        self.assertEqual(result.challenges, [self.challenge])
        self.assertEqual([k.kind for k in result.kinds], [self.chase])

    def test_level_filter_hides_kinds_above_the_actor(self) -> None:
        low = find_situations(query="heist", risk=None, actor_level_index=0)
        self.assertEqual(low.kinds, [])
        top = find_situations(query="heist", risk=None, actor_level_index=TOP)
        self.assertEqual([k.kind for k in top.kinds], [self.heist])

    def test_kind_result_carries_fits_guides_and_pools(self) -> None:
        result = find_situations(query="chase", risk=None, actor_level_index=0)
        kind = result.kinds[0]
        self.assertEqual(kind.check_fits, [self.fit])
        self.assertIsNone(kind.difficulty_guide)
        self.assertEqual(kind.all_guides, [self.low, self.high])
        self.assertEqual(kind.pool_guides, [self.pool_guide])

    def test_risk_picks_the_matching_guide(self) -> None:
        result = find_situations(query="chase", risk=RenownRisk.HIGH, actor_level_index=0)
        self.assertEqual(result.kinds[0].difficulty_guide, self.high)
        none = find_situations(query="chase", risk=RenownRisk.EXTREME, actor_level_index=0)
        self.assertIsNone(none.kinds[0].difficulty_guide)

    def test_query_count_is_flat_in_the_number_of_kinds(self) -> None:
        for i in range(4):
            kind = SituationKindFactory(name=f"Chase variant {i}")
            SituationDifficultyGuideFactory(situation_kind=kind, risk=RenownRisk.LOW)
        find_situations(query="", risk=None, actor_level_index=0)
        with self.assertNumQueries(5):
            result = find_situations(query="chase", risk=None, actor_level_index=0)
        self.assertEqual(len(result.kinds), 5)

    def test_result_limit_applies_to_templates(self) -> None:
        for i in range(20):
            SituationTemplateFactory(name=f"Chase scene {i:02d}")
        result = find_situations(query="chase", risk=None, actor_level_index=0)
        self.assertEqual(len(result.templates), 15)


class UserBreadthIndexTests(TestCase):
    def test_staff_gets_the_top_index_without_a_profile(self) -> None:
        self.assertEqual(user_breadth_index(AccountFactory(is_staff=True)), TOP)

    def test_gm_gets_their_level_index(self) -> None:
        account = AccountFactory()
        GMProfileFactory(account=account, level=GMLevel.EXPERIENCED)
        self.assertEqual(user_breadth_index(account), GM_LEVEL_ORDER.index(GMLevel.EXPERIENCED))

    def test_no_profile_is_starting_breadth(self) -> None:
        self.assertEqual(user_breadth_index(AccountFactory()), 0)
