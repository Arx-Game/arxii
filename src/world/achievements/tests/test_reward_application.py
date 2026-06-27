"""Achievement reward application (#1522): title / bonus / prestige granted on earn.

The reward-application engine: when an achievement is earned, its rewards attach to the
*character* — a CharacterTitle (cosmetic), a CharacterModifier on the bonus target (e.g. +5
allure), and a flat prestige bump — all applied by grant_achievement.
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

    def _add_reward(self, reward_type, *, value="", modifier_target=None) -> None:
        reward = RewardDefinitionFactory(reward_type=reward_type, modifier_target=modifier_target)
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
