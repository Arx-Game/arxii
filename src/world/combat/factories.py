"""FactoryBoy factories for combat models."""

import factory
from factory import django as factory_django

from world.combat.constants import (
    ActionCategory,
    ComboLearningMethod,
    EncounterType,
    OpponentTier,
    TargetingMode,
    TargetSelection,
)
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    ThreatPool,
    ThreatPoolEntry,
)


class CombatEncounterFactory(factory_django.DjangoModelFactory):
    """Factory for CombatEncounter."""

    class Meta:
        model = CombatEncounter

    encounter_type = EncounterType.PARTY_COMBAT


class ThreatPoolFactory(factory_django.DjangoModelFactory):
    """Factory for ThreatPool."""

    class Meta:
        model = ThreatPool

    name = factory.Sequence(lambda n: f"Threat Pool {n}")


class ThreatPoolEntryFactory(factory_django.DjangoModelFactory):
    """Factory for ThreatPoolEntry."""

    class Meta:
        model = ThreatPoolEntry

    pool = factory.SubFactory(ThreatPoolFactory)
    name = factory.Sequence(lambda n: f"Attack {n}")
    attack_category = ActionCategory.PHYSICAL
    base_damage = 10
    weight = 10
    targeting_mode = TargetingMode.SINGLE
    target_selection = TargetSelection.SPECIFIC_ROLE


class CombatOpponentFactory(factory_django.DjangoModelFactory):
    """Factory for CombatOpponent (default: MOOK tier)."""

    class Meta:
        model = CombatOpponent

    encounter = factory.SubFactory(CombatEncounterFactory)
    tier = OpponentTier.MOOK
    name = factory.Sequence(lambda n: f"Opponent {n}")
    health = 50
    max_health = 50
    threat_pool = factory.SubFactory(ThreatPoolFactory)


class BossOpponentFactory(CombatOpponentFactory):
    """Factory for a boss-tier CombatOpponent."""

    tier = OpponentTier.BOSS
    health = 500
    max_health = 500
    soak_value = 80
    probing_threshold = 50


class BossPhaseFactory(factory_django.DjangoModelFactory):
    """Factory for BossPhase."""

    class Meta:
        model = BossPhase

    opponent = factory.SubFactory(BossOpponentFactory)
    phase_number = factory.Sequence(lambda n: n + 1)
    threat_pool = factory.SubFactory(ThreatPoolFactory)


class CombatParticipantFactory(factory_django.DjangoModelFactory):
    """Factory for CombatParticipant."""

    class Meta:
        model = CombatParticipant

    encounter = factory.SubFactory(CombatEncounterFactory)
    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")


class ComboDefinitionFactory(factory_django.DjangoModelFactory):
    """Factory for ComboDefinition."""

    class Meta:
        model = ComboDefinition

    name = factory.Sequence(lambda n: f"Combo {n}")
    slug = factory.Sequence(lambda n: f"combo-{n}")
    description = "A powerful combo attack."
    bypass_soak = True
    bonus_damage = 50


class ComboSlotFactory(factory_django.DjangoModelFactory):
    """Factory for ComboSlot."""

    class Meta:
        model = ComboSlot

    combo = factory.SubFactory(ComboDefinitionFactory)
    slot_number = factory.Sequence(lambda n: n + 1)
    required_action_type = factory.SubFactory("world.magic.factories.EffectTypeFactory")


class ComboLearningFactory(factory_django.DjangoModelFactory):
    """Factory for ComboLearning."""

    class Meta:
        model = ComboLearning

    combo = factory.SubFactory(ComboDefinitionFactory)
    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    learned_via = ComboLearningMethod.TRAINING
