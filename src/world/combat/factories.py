"""FactoryBoy factories for combat models."""

import factory
from factory import django as factory_django

from world.combat.constants import (
    DEFAULT_PACE_TIMER_MINUTES,
    ActionCategory,
    ComboLearningMethod,
    EncounterType,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatPull,
    CombatPullResolvedEffect,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    ThreatPool,
    ThreatPoolEntry,
)
from world.magic.constants import EffectKind


class CombatEncounterFactory(factory_django.DjangoModelFactory):
    """Factory for CombatEncounter."""

    class Meta:
        model = CombatEncounter

    encounter_type = EncounterType.PARTY_COMBAT
    pace_mode = PaceMode.TIMED
    pace_timer_minutes = DEFAULT_PACE_TIMER_MINUTES

    @factory.lazy_attribute
    def room(self) -> object:
        from evennia import create_object

        return create_object("typeclasses.rooms.Room", key="Test Combat Room")


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
    """Factory for CombatOpponent.

    Default: ephemeral MOOK backed by a fresh CombatNPC at the encounter's room.
    When ``persona`` is supplied: uses the persona's character ObjectDB (non-ephemeral).

    Stores objectdb_id (FK integer, not the instance) to avoid caching an Evennia
    ObjectDB in the model's __dict__, which would break setUpTestData deepcopy
    (DbHolder is not deepcopyable).
    """

    class Meta:
        model = CombatOpponent

    encounter = factory.SubFactory(CombatEncounterFactory)
    tier = OpponentTier.MOOK
    name = factory.Sequence(lambda n: f"Opponent {n}")
    health = 50
    max_health = 50
    threat_pool = factory.SubFactory(ThreatPoolFactory)
    persona = None

    @factory.lazy_attribute
    def objectdb_is_ephemeral(self) -> bool:
        return self.persona is None

    @factory.lazy_attribute
    def objectdb_id(self) -> int | None:  # type: ignore[override]
        if self.persona is not None:
            return self.persona.character_sheet.character_id

        from evennia import create_object
        from evennia.objects.models import ObjectDB

        from world.combat.typeclasses.combat_npc import CombatNPC

        # Fetch the room via PK rather than encounter.room to avoid caching an
        # Evennia ObjectDB instance on the encounter's FK cache, which would break
        # setUpTestData deepcopy (DbHolder is not deepcopyable).
        room_id = self.encounter.room_id
        room = ObjectDB.objects.get(pk=room_id) if room_id else None
        npc = create_object(CombatNPC, key=self.name, location=room)
        return npc.pk


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
    status = ParticipantStatus.ACTIVE


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


# =============================================================================
# Resonance Pivot Spec A — Phase 6: CombatPull + CombatPullResolvedEffect
# =============================================================================


class CombatPullFactory(factory_django.DjangoModelFactory):
    """Factory for CombatPull.

    Encounter defaults to ``participant.encounter`` so the unique_together
    constraint (participant, round_number) is satisfied without callers having
    to supply it. Override ``encounter=...`` if you need a mismatched pair
    (services/tests should normally not).
    """

    class Meta:
        model = CombatPull

    participant = factory.SubFactory(CombatParticipantFactory)
    encounter = factory.SelfAttribute("participant.encounter")
    round_number = 1
    resonance = factory.SubFactory("world.magic.factories.ResonanceFactory")
    tier = 1
    resonance_spent = 1
    anima_spent = 1


class CombatPullResolvedEffectFactory(factory_django.DjangoModelFactory):
    """Factory for CombatPullResolvedEffect (default: FLAT_BONUS shape).

    Defaults satisfy clean() and DB CheckConstraints out-of-the-box. Override
    ``kind`` plus the matching payload fields to test other shapes; mirror the
    ThreadPullEffectFactory trait pattern in tests if needed.

    NOTE: this factory does NOT call full_clean(); kind/payload alignment is
    enforced at the DB layer via CheckConstraints (matches ThreadFactory style).
    """

    class Meta:
        model = CombatPullResolvedEffect

    pull = factory.SubFactory(CombatPullFactory)
    source_thread = factory.SubFactory("world.magic.factories.ThreadFactory")
    kind = EffectKind.FLAT_BONUS
    authored_value = 2
    level_multiplier = 2
    scaled_value = 4
    vital_target = None
    source_thread_level = 2
    source_tier = 1
    granted_capability = None
    narrative_snippet = ""


class CombatRoundActionFactory(factory_django.DjangoModelFactory):
    """Factory for CombatRoundAction."""

    class Meta:
        model = CombatRoundAction

    participant = factory.SubFactory(CombatParticipantFactory)
    round_number = 1
    focused_opponent_target = None
    focused_ally_target = None
