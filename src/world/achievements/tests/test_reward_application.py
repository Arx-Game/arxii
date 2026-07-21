"""Achievement reward application (#1522, #2037): title / bonus / prestige / distinction
granted on earn.

The reward-application engine: when an achievement is earned, its rewards attach to the
*character* — a CharacterTitle (cosmetic), a CharacterModifier on the bonus target (e.g. +5
allure), a flat prestige bump, and a Distinction grant/rank-up via the shared
``grant_distinction`` seam — all applied by grant_achievement.
"""

from django.test import TestCase

from world.achievements.constants import RewardType
from world.achievements.factories import (
    AchievementFactory,
    AchievementRewardFactory,
    RewardDefinitionFactory,
)
from world.achievements.models import CharacterTitle
from world.achievements.services import grant_achievement
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.mechanics.services import get_modifier_total


class RewardApplicationTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.achievement = AchievementFactory(name="Sample Rewarding Achievement")
        self.allure = ModifierTargetFactory(
            name="allure", category=ModifierCategoryFactory(name="roll_modifier")
        )

    def _add_reward(self, reward_type, *, value="", modifier_target=None, distinction=None) -> None:
        reward = RewardDefinitionFactory(
            reward_type=reward_type, modifier_target=modifier_target, distinction=distinction
        )
        AchievementRewardFactory(achievement=self.achievement, reward=reward, reward_value=value)

    def test_title_reward_grants_a_character_title(self) -> None:
        self._add_reward(RewardType.TITLE)
        grant_achievement(self.achievement, [self.sheet])
        assert CharacterTitle.objects.filter(character_sheet=self.sheet).count() == 1

    def test_bonus_reward_grants_a_modifier_read_by_get_modifier_total(self) -> None:
        self._add_reward(RewardType.BONUS, value="5", modifier_target=self.allure)
        grant_achievement(self.achievement, [self.sheet])
        mod = CharacterModifier.objects.get(character=self.sheet, target=self.allure)
        assert mod.source.source_type == "achievement_reward"
        # The achievement-sourced bonus is counted by the standard stat read.
        assert get_modifier_total(self.sheet, self.allure) == 5

    def test_prestige_reward_bumps_persona_prestige(self) -> None:
        self._add_reward(RewardType.PRESTIGE, value="5000")
        before = self.sheet.primary_persona.total_prestige
        grant_achievement(self.achievement, [self.sheet])
        self.sheet.primary_persona.refresh_from_db()
        assert self.sheet.primary_persona.total_prestige == before + 5000

    def test_all_three_rewards_apply_together(self) -> None:
        self._add_reward(RewardType.TITLE)
        self._add_reward(RewardType.BONUS, value="5", modifier_target=self.allure)
        self._add_reward(RewardType.PRESTIGE, value="5000")
        grant_achievement(self.achievement, [self.sheet])
        assert CharacterTitle.objects.filter(character_sheet=self.sheet).exists()
        assert get_modifier_total(self.sheet, self.allure) == 5
        self.sheet.primary_persona.refresh_from_db()
        assert self.sheet.primary_persona.total_prestige >= 5000

    def test_re_earning_does_not_double_apply(self) -> None:
        # grant only applies rewards for a NEWLY-earned sheet; re-granting is a no-op.
        self._add_reward(RewardType.BONUS, value="5", modifier_target=self.allure)
        grant_achievement(self.achievement, [self.sheet])
        grant_achievement(self.achievement, [self.sheet])
        # +5 once, not +10 — rewards apply only on the first (newly-earned) grant.
        assert get_modifier_total(self.sheet, self.allure) == 5


class DistinctionRewardApplicationTests(TestCase):
    """DISTINCTION reward type (#2037): grants/ranks-up via the shared grant_distinction seam."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.achievement = AchievementFactory(name="Sample Distinction Achievement")
        self.distinction = DistinctionFactory(name="Silver Tongue", max_rank=5)

    def _add_reward(self, *, value="", distinction=None) -> None:
        reward = RewardDefinitionFactory(
            reward_type=RewardType.DISTINCTION,
            distinction=distinction if distinction is not None else self.distinction,
        )
        AchievementRewardFactory(achievement=self.achievement, reward=reward, reward_value=value)

    def test_distinction_reward_grants_once_per_newly_earned(self) -> None:
        self._add_reward()

        grant_achievement(self.achievement, [self.sheet])

        assert (
            CharacterDistinction.objects.filter(
                character=self.sheet, distinction=self.distinction
            ).count()
            == 1
        )

    def test_distinction_reward_stamps_achievement_auto_grant_origin(self) -> None:
        self._add_reward()

        grant_achievement(self.achievement, [self.sheet])

        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=self.distinction)
        assert cd.origin == DistinctionOrigin.ACHIEVEMENT_AUTO_GRANT

    def test_explicit_reward_value_grants_that_rank(self) -> None:
        self._add_reward(value="3")

        grant_achievement(self.achievement, [self.sheet])

        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=self.distinction)
        assert cd.rank == 3

    def test_blank_reward_value_steps_rank(self) -> None:
        self._add_reward(value="")

        grant_achievement(self.achievement, [self.sheet])

        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=self.distinction)
        assert cd.rank == 1

    def test_garbage_reward_value_steps_rank(self) -> None:
        self._add_reward(value="not-a-number")

        grant_achievement(self.achievement, [self.sheet])

        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=self.distinction)
        assert cd.rank == 1

    def test_negative_reward_value_steps_rank_and_sibling_rewards_still_apply(self) -> None:
        # A staff-authored reward_value="-1" must not reach grant_distinction as a raw
        # negative rank (rank is a PositiveIntegerField -> IntegrityError -> the whole
        # grant_achievement transaction rolls back, including sibling rewards). Non-positive
        # parses fall back to rank=None (advance-one), same as blank/garbage (#2037 review
        # fold-in).
        self._add_reward(value="-1")
        title_reward = RewardDefinitionFactory(reward_type=RewardType.TITLE)
        AchievementRewardFactory(achievement=self.achievement, reward=title_reward)

        grant_achievement(self.achievement, [self.sheet])

        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=self.distinction)
        assert cd.rank == 1
        assert CharacterTitle.objects.filter(character_sheet=self.sheet).exists()

    def test_re_earning_does_not_double_rank_up(self) -> None:
        self._add_reward()
        grant_achievement(self.achievement, [self.sheet])
        grant_achievement(self.achievement, [self.sheet])

        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=self.distinction)
        assert cd.rank == 1

    def test_exclusion_conflict_skips_the_distinction_leg_and_continues(self) -> None:
        # Sheet already holds a distinction mutually exclusive with the reward's.
        conflicting = DistinctionFactory(name="Iron Will")
        self.distinction.mutually_exclusive_with.add(conflicting)
        CharacterDistinctionFactory(character=self.sheet, distinction=conflicting, rank=1)
        self._add_reward()
        # A second, unrelated reward on the same achievement — proves the exclusion
        # conflict on the distinction leg doesn't crash the rest of the award.
        title_reward = RewardDefinitionFactory(reward_type=RewardType.TITLE)
        AchievementRewardFactory(achievement=self.achievement, reward=title_reward)

        grant_achievement(self.achievement, [self.sheet])

        assert not CharacterDistinction.objects.filter(
            character=self.sheet, distinction=self.distinction
        ).exists()
        assert CharacterTitle.objects.filter(character_sheet=self.sheet).exists()
