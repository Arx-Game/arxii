import factory
from factory import django as factory_django

from world.achievements.constants import ComparisonType, NotificationLevel, RewardType
from world.achievements.models import (
    Achievement,
    AchievementRequirement,
    AchievementReward,
    CharacterAchievement,
    Discovery,
    RewardDefinition,
    StatDefinition,
    StatTracker,
)
from world.character_sheets.factories import CharacterSheetFactory


class StatDefinitionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StatDefinition
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"test.stat.{n}")
    name = factory.LazyAttribute(lambda o: o.key.replace(".", " ").title())
    description = ""


class StatTrackerFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StatTracker
        django_get_or_create = ("character_sheet", "stat")

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    stat = factory.SubFactory(StatDefinitionFactory)
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
    stat = factory.SubFactory(StatDefinitionFactory)
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


class RewardDefinitionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = RewardDefinition
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"test.reward.{n}")
    name = factory.LazyAttribute(lambda o: o.key.replace(".", " ").title())
    reward_type = RewardType.TITLE
    description = ""


class AchievementRewardFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = AchievementReward

    achievement = factory.SubFactory(AchievementFactory)
    reward = factory.SubFactory(RewardDefinitionFactory)
    reward_value = ""
