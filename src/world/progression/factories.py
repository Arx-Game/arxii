"""
Factory classes for progression models.
"""

from decimal import Decimal
import random

import factory
import factory.django as factory_django

from world.progression.models import (
    CharacterPathHistory,
    CharacterUnlock,
    CharacterXP,
    CharacterXPTransaction,
    CodexKnowledgeRequirement,
    DevelopmentPoints,
    DevelopmentTransaction,
    DuranceTrainingSite,
    ExperiencePointsData,
    KudosClaimCategory,
    KudosDifficultyWeight,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
    PathIntent,
    RandomSceneTarget,
    WeeklySkillUsage,
    WeeklySocialEngagement,
    XPTransaction,
)
from world.progression.types import DevelopmentSource, ProgressionReason

# Module path imported lazily inside LazyFunctions to fetch the current game week;
# extracted to a single constant to satisfy S1192.
_WEEK_SERVICES_MODULE = "world.game_clock.week_services"


class ExperiencePointsDataFactory(factory_django.DjangoModelFactory):
    """Factory for ExperiencePointsData."""

    class Meta:
        model = ExperiencePointsData

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    total_earned = factory.Faker("random_int", min=0, max=1000)
    total_spent = factory.LazyAttribute(
        lambda obj: random.randint(0, obj.total_earned),  # noqa: S311
    )


class XPTransactionFactory(factory_django.DjangoModelFactory):
    """Factory for XPTransaction."""

    class Meta:
        model = XPTransaction

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    amount = factory.Faker("random_int", min=-100, max=100)
    reason = factory.Faker(
        "random_element",
        elements=[choice[0] for choice in ProgressionReason.choices],
    )
    description = factory.Faker("sentence")


class DevelopmentPointsFactory(factory_django.DjangoModelFactory):
    """Factory for DevelopmentPoints."""

    class Meta:
        model = DevelopmentPoints

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    trait = factory.SubFactory("world.traits.factories.TraitFactory")
    total_earned = factory.Faker("random_int", min=0, max=100)


class DevelopmentTransactionFactory(factory_django.DjangoModelFactory):
    """Factory for DevelopmentTransaction."""

    class Meta:
        model = DevelopmentTransaction

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    trait = factory.SubFactory("world.traits.factories.TraitFactory")
    source = factory.Faker(
        "random_element",
        elements=[choice[0] for choice in DevelopmentSource.choices],
    )
    amount = factory.Faker("random_int", min=1, max=10)
    reason = factory.Faker(
        "random_element",
        elements=[choice[0] for choice in ProgressionReason.choices],
    )
    description = factory.Faker("sentence")


class CharacterUnlockFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterUnlock."""

    class Meta:
        model = CharacterUnlock

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    character_class = factory.SubFactory(
        "world.classes.factories.CharacterClassFactory",
    )
    target_level = factory.Faker("random_int", min=1, max=10)
    xp_spent = factory.Faker("random_int", min=0, max=50)


class CharacterPathHistoryFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterPathHistory."""

    class Meta:
        model = CharacterPathHistory

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    path = factory.SubFactory("world.classes.factories.PathFactory")


class KudosSourceCategoryFactory(factory_django.DjangoModelFactory):
    """Factory for KudosSourceCategory."""

    class Meta:
        model = KudosSourceCategory

    name = factory.Sequence(lambda n: f"source_{n}")
    display_name = factory.LazyAttribute(lambda obj: obj.name.replace("_", " ").title())
    description = factory.Faker("sentence")
    default_amount = factory.Faker("random_int", min=1, max=10)
    is_active = True
    staff_only = False


class KudosClaimCategoryFactory(factory_django.DjangoModelFactory):
    """Factory for KudosClaimCategory."""

    class Meta:
        model = KudosClaimCategory

    name = factory.Sequence(lambda n: f"claim_{n}")
    display_name = factory.LazyAttribute(lambda obj: obj.name.replace("_", " ").title())
    description = factory.Faker("sentence")
    kudos_cost = factory.Faker("random_int", min=5, max=20)
    reward_amount = factory.Faker("random_int", min=1, max=10)
    is_active = True


class KudosPointsDataFactory(factory_django.DjangoModelFactory):
    """Factory for KudosPointsData."""

    class Meta:
        model = KudosPointsData

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    total_earned = factory.Faker("random_int", min=0, max=500)
    total_claimed = factory.LazyAttribute(
        lambda obj: random.randint(0, obj.total_earned),  # noqa: S311
    )


class KudosTransactionFactory(factory_django.DjangoModelFactory):
    """Factory for KudosTransaction (award type)."""

    class Meta:
        model = KudosTransaction

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    amount = factory.Faker("random_int", min=1, max=20)
    source_category = factory.SubFactory(KudosSourceCategoryFactory)
    claim_category = None
    description = factory.Faker("sentence")


class CharacterXPFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterXP."""

    class Meta:
        model = CharacterXP

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    total_earned = factory.Faker("random_int", min=0, max=500)
    total_spent = factory.LazyAttribute(
        lambda obj: random.randint(0, obj.total_earned),  # noqa: S311
    )
    transferable = True


class CharacterXPTransactionFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterXPTransaction."""

    class Meta:
        model = CharacterXPTransaction

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    amount = factory.Faker("random_int", min=1, max=100)
    reason = ProgressionReason.SYSTEM_AWARD
    description = factory.Faker("sentence")
    transferable = True


class WeeklySkillUsageFactory(factory_django.DjangoModelFactory):
    """Factory for WeeklySkillUsage."""

    class Meta:
        model = WeeklySkillUsage

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    trait = factory.SubFactory("world.traits.factories.TraitFactory")
    game_week = factory.LazyFunction(
        lambda: __import__(
            _WEEK_SERVICES_MODULE, fromlist=["get_current_game_week"]
        ).get_current_game_week()
    )
    points_earned = 0
    check_count = 0
    processed = False


class KudosDifficultyWeightFactory(factory_django.DjangoModelFactory):
    """Factory for KudosDifficultyWeight."""

    class Meta:
        model = KudosDifficultyWeight

    difficulty_choice = factory.Iterator(["trivial", "easy", "normal", "hard", "daunting"])
    multiplier = Decimal("1.00")


# Default seed weights: lower difficulty = higher multiplier (easier to trigger
# affectable actions → more generous reward); harder = lower multiplier.
_DEFAULT_BAND_WEIGHTS: dict[str, Decimal] = {
    "trivial": Decimal("2.00"),
    "easy": Decimal("1.50"),
    "normal": Decimal("1.00"),
    "hard": Decimal("0.50"),
    "daunting": Decimal("0.25"),
}


class WeeklySocialEngagementFactory(factory_django.DjangoModelFactory):
    """Factory for WeeklySocialEngagement."""

    class Meta:
        model = WeeklySocialEngagement

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    game_week = factory.LazyFunction(
        lambda: __import__(
            _WEEK_SERVICES_MODULE, fromlist=["get_current_game_week"]
        ).get_current_game_week()
    )
    pending_points = Decimal(0)
    granted = False


class RandomSceneTargetFactory(factory_django.DjangoModelFactory):
    """Factory for RandomSceneTarget."""

    class Meta:
        model = RandomSceneTarget

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    target_persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    game_week = factory.LazyFunction(
        lambda: __import__(
            _WEEK_SERVICES_MODULE, fromlist=["get_current_game_week"]
        ).get_current_game_week()
    )
    slot_number = 1
    claimed = False
    first_time = True
    rerolled = False


class PathIntentFactory(factory_django.DjangoModelFactory):
    """Factory for PathIntent."""

    class Meta:
        model = PathIntent

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    intended_path = factory.SubFactory("world.classes.factories.PathFactory")


class DuranceTrainingSiteFactory(factory_django.DjangoModelFactory):
    """Factory for DuranceTrainingSite."""

    class Meta:
        model = DuranceTrainingSite

    room_profile = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    officiant = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    is_active = True


def seed_kudos_difficulty_weights() -> None:
    """
    Create the default KudosDifficultyWeight rows via get_or_create.

    Idempotent: safe to call multiple times; existing rows are not modified.
    Doubles as integration-test setUp data and new-game seed data.
    """
    for band, weight in _DEFAULT_BAND_WEIGHTS.items():
        KudosDifficultyWeight.objects.get_or_create(
            difficulty_choice=band,
            defaults={"multiplier": weight},
        )


class CodexKnowledgeRequirementFactory(factory_django.DjangoModelFactory):
    """Factory for CodexKnowledgeRequirement (#2603)."""

    class Meta:
        model = CodexKnowledgeRequirement

    codex_entry = factory.SubFactory("world.codex.factories.CodexEntryFactory")
    path = factory.SubFactory("world.classes.factories.PathFactory")
