from django.db import IntegrityError
from django.test import TestCase

from world.achievements.constants import ComparisonType
from world.achievements.factories import (
    AchievementFactory,
    AchievementRequirementFactory,
    AchievementRewardFactory,
    CharacterAchievementFactory,
    DiscoveryFactory,
    RewardDefinitionFactory,
    StatDefinitionFactory,
    StatTrackerFactory,
)
from world.achievements.models import Achievement, RewardDefinition, StatDefinition, StatTracker


class StatDefinitionModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.stat_def = StatDefinitionFactory(key="quests.completed", name="Quests Completed")

    def test_str(self) -> None:
        self.assertEqual(str(self.stat_def), "Quests Completed (quests.completed)")

    def test_unique_key(self) -> None:
        with self.assertRaises(IntegrityError):
            StatDefinition.objects.create(key="quests.completed", name="Duplicate")


class StatTrackerModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.stat_def = StatDefinitionFactory(key="quests_completed", name="Quests Completed")
        cls.tracker = StatTrackerFactory(stat=cls.stat_def, value=5)

    def test_str(self) -> None:
        expected = f"{self.tracker.character_sheet} - quests_completed: 5"
        self.assertEqual(str(self.tracker), expected)

    def test_default_value_is_zero(self) -> None:
        tracker = StatTrackerFactory()
        self.assertEqual(tracker.value, 0)

    def test_unique_constraint_character_stat(self) -> None:
        with self.assertRaises(IntegrityError):
            StatTracker.objects.create(
                character_sheet=self.tracker.character_sheet,
                stat=self.stat_def,
            )


class AchievementModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.achievement = AchievementFactory(name="Dragon Slayer", slug="dragon-slayer")

    def test_str(self) -> None:
        self.assertEqual(str(self.achievement), "Dragon Slayer")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            AchievementFactory(name="Dragon Slayer", slug="dragon-slayer-2")

    def test_unique_slug(self) -> None:
        with self.assertRaises(IntegrityError):
            Achievement.objects.create(
                name="Dragon Slayer 2",
                slug="dragon-slayer",
                description="Duplicate slug test",
            )

    def test_hidden_by_default(self) -> None:
        achievement = AchievementFactory()
        self.assertTrue(achievement.hidden)

    def test_chain_prerequisite(self) -> None:
        novice = AchievementFactory(name="Novice Explorer", slug="novice-explorer")
        seasoned = AchievementFactory(
            name="Seasoned Explorer", slug="seasoned-explorer", prerequisite=novice
        )
        self.assertEqual(seasoned.prerequisite, novice)
        self.assertIn(seasoned, novice.next_in_chain.all())


class AchievementRequirementModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.stat_def = StatDefinitionFactory(key="kills", name="Kills")
        cls.achievement = AchievementFactory(name="Test Achievement", slug="test-achievement")
        cls.requirement = AchievementRequirementFactory(
            achievement=cls.achievement, stat=cls.stat_def, threshold=10
        )

    def test_str(self) -> None:
        expected = "Test Achievement: kills Greater than or equal 10"
        self.assertEqual(str(self.requirement), expected)

    def test_multiple_requirements_per_achievement(self) -> None:
        quests_stat = StatDefinitionFactory(key="quests", name="Quests")
        AchievementRequirementFactory(
            achievement=self.achievement,
            stat=quests_stat,
            threshold=5,
            comparison=ComparisonType.GTE,
        )
        self.assertEqual(self.achievement.requirements.count(), 2)

    def test_is_met_gte(self) -> None:
        req = AchievementRequirementFactory(threshold=10, comparison=ComparisonType.GTE)
        self.assertFalse(req.is_met(9))
        self.assertTrue(req.is_met(10))
        self.assertTrue(req.is_met(11))

    def test_is_met_eq(self) -> None:
        req = AchievementRequirementFactory(threshold=10, comparison=ComparisonType.EQ)
        self.assertFalse(req.is_met(9))
        self.assertTrue(req.is_met(10))
        self.assertFalse(req.is_met(11))

    def test_is_met_lte(self) -> None:
        req = AchievementRequirementFactory(threshold=10, comparison=ComparisonType.LTE)
        self.assertTrue(req.is_met(9))
        self.assertTrue(req.is_met(10))
        self.assertFalse(req.is_met(11))


class DiscoveryModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.achievement = AchievementFactory(name="Hidden Gem", slug="hidden-gem")
        cls.discovery = DiscoveryFactory(achievement=cls.achievement)

    def test_str(self) -> None:
        self.assertEqual(str(self.discovery), "Discovery: Hidden Gem")

    def test_one_discovery_per_achievement(self) -> None:
        with self.assertRaises(IntegrityError):
            DiscoveryFactory(achievement=self.achievement)


class CharacterAchievementModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.char_achievement = CharacterAchievementFactory()

    def test_str(self) -> None:
        expected = (
            f"{self.char_achievement.character_sheet} - {self.char_achievement.achievement.name}"
        )
        self.assertEqual(str(self.char_achievement), expected)

    def test_unique_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            CharacterAchievementFactory(
                character_sheet=self.char_achievement.character_sheet,
                achievement=self.char_achievement.achievement,
            )

    def test_discovery_link(self) -> None:
        discovery = DiscoveryFactory()
        char_achievement = CharacterAchievementFactory(
            achievement=discovery.achievement, discovery=discovery
        )
        self.assertEqual(char_achievement.discovery, discovery)
        self.assertIn(char_achievement, discovery.discoverers.all())


class RewardDefinitionModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reward_def = RewardDefinitionFactory(key="title.champion", name="Champion")

    def test_str(self) -> None:
        self.assertEqual(str(self.reward_def), "Champion (title.champion)")

    def test_unique_key(self) -> None:
        with self.assertRaises(IntegrityError):
            RewardDefinition.objects.create(
                key="title.champion", name="Duplicate", reward_type="title"
            )


class AchievementRewardModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reward = AchievementRewardFactory()

    def test_str(self) -> None:
        expected = f"{self.reward.achievement.name}: {self.reward.reward.name}"
        self.assertEqual(str(self.reward), expected)
