import factory
from factory import django as factory_django

from world.achievements.constants import ComparisonType, NotificationLevel, RewardType
from world.achievements.models import (
    Achievement,
    AchievementRequirement,
    AchievementReward,
    CharacterAchievement,
    Discovery,
    StatTracker,
)
from world.character_sheets.factories import CharacterSheetFactory


class StatTrackerFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StatTracker
        django_get_or_create = ("character_sheet", "stat_key")

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    stat_key = factory.Sequence(lambda n: f"test.stat.{n}")
    value = 0


class AchievementFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Achievement
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Achievement {n}")
    slug = factory.Sequence(lambda n: f"achievement-{n}")
    description = factory.Faker("sentence")
    hidden = True
    notification_level = NotificationLevel.PERSONAL
    is_active = True


class AchievementRequirementFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = AchievementRequirement

    achievement = factory.SubFactory(AchievementFactory)
    stat_key = "test.stat.0"
    threshold = 1
    comparison = ComparisonType.GTE


class DiscoveryFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Discovery

    achievement = factory.SubFactory(AchievementFactory)


class CharacterAchievementFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CharacterAchievement

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    achievement = factory.SubFactory(AchievementFactory)


class AchievementRewardFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = AchievementReward

    achievement = factory.SubFactory(AchievementFactory)
    reward_type = RewardType.TITLE
    reward_key = "test_title"
    reward_value = ""
    description = "A test reward"
