from django.db import IntegrityError
from django.test import TestCase

from world.achievements.constants import ComparisonType
from world.achievements.factories import (
    AchievementFactory,
    AchievementRequirementFactory,
    AchievementRewardFactory,
    CharacterAchievementFactory,
    DiscoveryFactory,
    StatTrackerFactory,
)
from world.achievements.models import Achievement, StatTracker


class StatTrackerModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tracker = StatTrackerFactory(stat_key="quests_completed", value=5)

    def test_str(self) -> None:
        expected = f"{self.tracker.character_sheet} - quests_completed: 5"
        self.assertEqual(str(self.tracker), expected)

    def test_default_value_is_zero(self) -> None:
        tracker = StatTrackerFactory(stat_key="new_stat")
        self.assertEqual(tracker.value, 0)

    def test_unique_together_character_stat_key(self) -> None:
        with self.assertRaises(IntegrityError):
            StatTracker.objects.create(
                character_sheet=self.tracker.character_sheet,
                stat_key="quests_completed",
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
        cls.achievement = AchievementFactory(name="Test Achievement", slug="test-achievement")
        cls.requirement = AchievementRequirementFactory(
            achievement=cls.achievement, stat_key="kills", threshold=10
        )

    def test_str(self) -> None:
        expected = "Test Achievement: kills Greater than or equal 10"
        self.assertEqual(str(self.requirement), expected)

    def test_multiple_requirements_per_achievement(self) -> None:
        AchievementRequirementFactory(
            achievement=self.achievement,
            stat_key="quests",
            threshold=5,
            comparison=ComparisonType.GTE,
        )
        self.assertEqual(self.achievement.requirements.count(), 2)


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

    def test_unique_together(self) -> None:
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


class AchievementRewardModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reward = AchievementRewardFactory()

    def test_str(self) -> None:
        expected = f"{self.reward.achievement.name}: Title - A test reward"
        self.assertEqual(str(self.reward), expected)
