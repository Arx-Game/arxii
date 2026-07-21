"""FactoryBoy factories for combat models."""

from decimal import Decimal

import factory
from factory import django as factory_django

from world.combat.constants import (
    DEFAULT_PACE_TIMER_MINUTES,
    DEFAULT_RISK_MULTIPLIERS,
    DEFAULT_STAKES_REQUIREMENTS,
    DEFAULT_TIER_TEMPLATES,
    SCALING_CONFIG_BASELINE_PARTY_SIZE,
    SCALING_CONFIG_PER_AVG_LEVEL_PCT,
    SCALING_CONFIG_PER_EXTRA_MEMBER_PCT,
    ActionCategory,
    ClashActionSlot,
    ClashFlavor,
    ComboLearningMethod,
    DuelChallengeStatus,
    EncounterOutcome,
    EncounterType,
    EngagementLockStatus,
    LockInitiator,
    LockPcRole,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
    TargetingMode,
    TargetSelection,
)
from world.combat.models import (
    BossPhase,
    BreakBarConfig,
    Clash,
    ClashConfig,
    ClashContribution,
    ClashRound,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatPull,
    CombatPullResolvedEffect,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    CreaturePhaseTemplate,
    CreatureTemplate,
    DuelChallenge,
    EncounterAftermathRule,
    EncounterScalingConfig,
    EngagementLock,
    EscalationCurve,
    OpponentTierTemplate,
    RiskScalingModifier,
    StakesLevelRequirement,
    StrainConfig,
    ThreatPool,
    ThreatPoolEntry,
    ThreatRecord,
)
from world.gm.constants import GMLevel
from world.magic.constants import EffectKind

# Factory-path string for the CharacterSheet sub-factory, referenced by
# multiple factories below. Centralized to avoid the duplicated-literal
# SonarCloud smell (python:S1192).
_CHARACTER_SHEET_FACTORY = "world.character_sheets.factories.CharacterSheetFactory"
_ROOM_TYPECLASS = "typeclasses.rooms.Room"


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

        return create_object(_ROOM_TYPECLASS, key="Test Combat Room", nohome=True)

    @factory.lazy_attribute
    def scene(self) -> object:
        from world.scenes.factories import SceneFactory

        return SceneFactory(location=self.room)


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
    damage_type = None
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
    affinity = ""

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
        npc = create_object(CombatNPC, key=self.name, location=room, nohome=True)
        return npc.pk


class BossOpponentFactory(CombatOpponentFactory):
    """Factory for a boss-tier CombatOpponent."""

    tier = OpponentTier.BOSS
    health = 500
    max_health = 500
    soak_value = 80
    probing_threshold = 50


class SwarmOpponentFactory(CombatOpponentFactory):
    """A swarm-tier opponent: count-based fodder, no soak.

    health/max_health are required columns but unused for swarms (damage
    routes through swarm_count). Defaults: 30 bodies, 5 damage per body,
    one outgoing attack per 6 bodies.
    """

    tier = OpponentTier.SWARM
    health = 1
    max_health = 1
    soak_value = 0
    swarm_count = 30
    max_swarm_count = 30
    body_toughness = 5
    bodies_per_attack = 6


class HeroKillerOpponentFactory(CombatOpponentFactory):
    """A Hero Killer: unbeatable endgame threat — PCs must flee."""

    tier = OpponentTier.HERO_KILLER
    health = 9999
    max_health = 9999
    soak_value = 200


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
    character_sheet = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
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
    character_sheet = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
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


class CombatOpponentActionFactory(factory_django.DjangoModelFactory):
    """Factory for CombatOpponentAction."""

    class Meta:
        model = CombatOpponentAction

    opponent = factory.SubFactory(CombatOpponentFactory)
    round_number = 1
    threat_entry = factory.SubFactory(ThreatPoolEntryFactory)


# =============================================================================
# Clash factories (Task 1.7)
# =============================================================================


class StrainConfigFactory(factory_django.DjangoModelFactory):
    """Factory for StrainConfig singleton (pk=1)."""

    class Meta:
        model = StrainConfig
        django_get_or_create = ("pk",)

    pk = 1
    base_anima_fatigue_ratio = 25
    strain_anima_fatigue_ratio = 50


class ClashConfigFactory(factory_django.DjangoModelFactory):
    """Factory for ClashConfig singleton (pk=1)."""

    class Meta:
        model = ClashConfig
        django_get_or_create = ("pk",)

    pk = 1


class ClashFactory(factory_django.DjangoModelFactory):
    """Factory for a CLASH-flavor Clash (the default flavor).

    CLASH is the only flavor that requires ``npc_win_threshold``; the other
    three flavors must have it null.  Per-flavor subclasses override the fields
    that change so that every row passes ``Clash.clean()``.

    Uses SubFactory for encounter and npc_opponent (mirrors CombatPullFactory).
    The npc_opponent is created without an ObjectDB to avoid the setUpTestData
    deepcopy restriction; this mirrors the inline creation pattern in
    ClashModelTests.setUp().
    """

    class Meta:
        model = Clash

    encounter = factory.SubFactory(CombatEncounterFactory)

    @factory.lazy_attribute
    def npc_opponent(self) -> CombatOpponent:
        return CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name=f"Clash NPC {self.encounter.pk}",
            health=50,
            max_health=50,
        )

    resolution_consequence_pool = factory.SubFactory("actions.factories.ConsequencePoolFactory")
    flavor = ClashFlavor.CLASH
    progress = 0
    pc_win_threshold = 5
    # CLASH flavor: npc_win_threshold required, lock_pc_role and ward_ends_on_round null
    npc_win_threshold = -5
    lock_pc_role = None
    ward_ends_on_round = None
    started_round = 1


class LockClashFactory(ClashFactory):
    """Factory for a LOCK-flavor Clash.

    Overrides flavor-coupled fields so the row passes Clash.clean():
    - flavor = LOCK
    - lock_pc_role = SUSTAINING (required for LOCK)
    - npc_win_threshold = None (must be null for non-CLASH flavors)
    """

    flavor = ClashFlavor.LOCK
    lock_pc_role = LockPcRole.SUSTAINING
    npc_win_threshold = None


class WardClashFactory(ClashFactory):
    """Factory for a WARD-flavor Clash.

    Overrides flavor-coupled fields so the row passes Clash.clean():
    - flavor = WARD
    - ward_ends_on_round = 5 (required for WARD)
    - npc_win_threshold = None (must be null for non-CLASH flavors)
    """

    flavor = ClashFlavor.WARD
    ward_ends_on_round = 5
    npc_win_threshold = None


class BreakClashFactory(ClashFactory):
    """Factory for a BREAK-flavor Clash.

    BREAK has no flavored field of its own; only npc_win_threshold must be null.
    """

    flavor = ClashFlavor.BREAK
    npc_win_threshold = None


class ClashRoundFactory(factory_django.DjangoModelFactory):
    """Factory for ClashRound."""

    class Meta:
        model = ClashRound

    clash = factory.SubFactory(ClashFactory)
    round_number = 1
    pc_progress_delta = 1
    npc_progress_delta = 0
    progress_after = 1


class ClashContributionFactory(factory_django.DjangoModelFactory):
    """Factory for ClashContribution."""

    class Meta:
        model = ClashContribution

    clash_round = factory.SubFactory(ClashRoundFactory)
    character = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
    action_slot = ClashActionSlot.FOCUSED
    anima_committed = 10
    check_outcome = factory.SubFactory("world.traits.factories.CheckOutcomeFactory")
    progress_delta = 1


class EncounterAftermathRuleFactory(factory_django.DjangoModelFactory):
    """Factory for EncounterAftermathRule (#876)."""

    class Meta:
        model = EncounterAftermathRule

    outcome = EncounterOutcome.DEFEAT
    risk_level = RiskLevel.MODERATE
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    base_difficulty = 25
    consequence_pool = None


# =============================================================================
# Encounter scaling factories (#566)
# =============================================================================


class OpponentTierTemplateFactory(factory_django.DjangoModelFactory):
    """Factory for OpponentTierTemplate (one row per tier)."""

    class Meta:
        model = OpponentTierTemplate
        django_get_or_create = ("tier",)

    tier = OpponentTier.MOOK
    base_health = 30
    base_soak = 0
    base_probing_threshold = None
    base_swarm_count = None
    body_toughness = None
    bodies_per_attack = None
    barrier_strength = None
    boss_phase_count = 1
    base_actions_per_round = 1


class CreatureTemplateFactory(factory_django.DjangoModelFactory):
    """Factory for CreatureTemplate."""

    class Meta:
        model = CreatureTemplate

    name = factory.Sequence(lambda n: f"Creature {n}")
    tier = OpponentTier.BOSS


class CreaturePhaseTemplateFactory(factory_django.DjangoModelFactory):
    """Factory for CreaturePhaseTemplate."""

    class Meta:
        model = CreaturePhaseTemplate

    creature_template = factory.SubFactory(CreatureTemplateFactory)
    phase_number = 1
    soak_value = 5
    health_trigger_percentage = 1.0


class BreakBarConfigFactory(factory_django.DjangoModelFactory):
    """Factory for BreakBarConfig."""

    class Meta:
        model = BreakBarConfig

    boss_phase = factory.SubFactory(CreaturePhaseTemplateFactory)
    max_threshold = 30
    vulnerability_rounds = 2
    intensity_bonus = 2


class RiskScalingModifierFactory(factory_django.DjangoModelFactory):
    """Factory for RiskScalingModifier (one row per risk level)."""

    class Meta:
        model = RiskScalingModifier
        django_get_or_create = ("risk_level",)

    risk_level = RiskLevel.MODERATE
    multiplier = Decimal("1.00")


class StakesLevelRequirementFactory(factory_django.DjangoModelFactory):
    """Factory for StakesLevelRequirement (one row per stakes level)."""

    class Meta:
        model = StakesLevelRequirement
        django_get_or_create = ("stakes_level",)

    stakes_level = StakesLevel.LOCAL
    minimum_party_average_level = 0
    minimum_gm_level = GMLevel.STARTING


class EncounterScalingConfigFactory(factory_django.DjangoModelFactory):
    """Factory for EncounterScalingConfig singleton (pk=1)."""

    class Meta:
        model = EncounterScalingConfig
        django_get_or_create = ("pk",)

    pk = 1
    baseline_party_size = SCALING_CONFIG_BASELINE_PARTY_SIZE
    per_extra_member_pct = Decimal(SCALING_CONFIG_PER_EXTRA_MEMBER_PCT)
    per_avg_level_pct = Decimal(SCALING_CONFIG_PER_AVG_LEVEL_PCT)
    updated_by = None


def seed_scaling_defaults() -> EncounterScalingConfig:
    """Seed all four encounter-scaling config tables with authored defaults (#566).

    Idempotent on row identity (one row per enum value / the pk=1 singleton),
    but NOT edit-preserving: it uses update_or_create at every layer, so
    re-running RESETS every row to the authored defaults, overwriting any staff
    edits. This is intentional for pre-launch seeding from authored constants;
    do not call it where staff tuning must survive.

    Creates/updates:
    - One OpponentTierTemplate per OpponentTier (5 rows)
    - One RiskScalingModifier per RiskLevel (5 rows)
    - One StakesLevelRequirement per StakesLevel (5 rows)
    - EncounterScalingConfig pk=1 singleton

    Returns the EncounterScalingConfig singleton.
    """
    for tier, stats in DEFAULT_TIER_TEMPLATES.items():
        OpponentTierTemplate.objects.update_or_create(tier=tier, defaults=stats)

    for risk_level, multiplier in DEFAULT_RISK_MULTIPLIERS.items():
        RiskScalingModifier.objects.update_or_create(
            risk_level=risk_level,
            defaults={"multiplier": Decimal(multiplier)},
        )

    for stakes_level, reqs in DEFAULT_STAKES_REQUIREMENTS.items():
        StakesLevelRequirement.objects.update_or_create(
            stakes_level=stakes_level,
            defaults=reqs,
        )

    config, _ = EncounterScalingConfig.objects.update_or_create(
        pk=1,
        defaults={
            "baseline_party_size": SCALING_CONFIG_BASELINE_PARTY_SIZE,
            "per_extra_member_pct": Decimal(SCALING_CONFIG_PER_EXTRA_MEMBER_PCT),
            "per_avg_level_pct": Decimal(SCALING_CONFIG_PER_AVG_LEVEL_PCT),
        },
    )
    return config


# =============================================================================
# Playable combat scenario — composition helper, not a DjangoModelFactory.
# =============================================================================


from dataclasses import dataclass  # noqa: E402


@dataclass
class PlayableCombatScenario:
    """All the entities needed for a fully-playable combat encounter.

    Built by ``PlayableCombatScenarioFactory.create()``. Holds references
    to every entity in the scenario so tests / demo paths can interact
    with each one directly.
    """

    scene: object
    encounter: CombatEncounter
    participants: list[CombatParticipant]
    opponent: CombatOpponent
    clash: Clash
    threat_pool: ThreatPool
    threat_entry: ThreatPoolEntry


class PlayableCombatScenarioFactory:
    """Compose a complete combat scenario in one call.

    Wires a Scene + CombatEncounter (in DECLARING status) + 2 PC
    CombatParticipants (with character sheets, vitals, anima, a clash-capable
    technique) + 1 NPC CombatOpponent + an active Clash on a threat-entry.

    Used by:
      - The full UI round-trip integration test as a setUp.
      - The future ``just demo-combat`` recipe to spawn a playable scenario
        for a logged-in dev user.

    Sensible defaults; everything is overridable at the kwargs level via
    a subsequent customization pass.
    """

    @classmethod
    def create(
        cls,
        *,
        num_pcs: int = 2,
        npc_name: str = "Practice Dummy",
        round_number: int = 1,
    ) -> PlayableCombatScenario:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterAnimaFactory,
            CharacterResonanceFactory,
            CharacterTechniqueFactory,
            ResonanceFactory,
            TechniqueFactory,
            ThreadFactory,
        )
        from world.scenes.constants import RoundStatus
        from world.scenes.factories import SceneFactory
        from world.vitals.models import CharacterVitals

        # Singletons (idempotent via django_get_or_create).
        ClashConfigFactory()
        StrainConfigFactory()

        # Scene + encounter.
        scene = SceneFactory()
        encounter = CombatEncounterFactory(
            scene=scene,
            status=RoundStatus.DECLARING,
            round_number=round_number,
        )

        # PCs.
        participants: list[CombatParticipant] = []
        resonance = ResonanceFactory()
        for _ in range(num_pcs):
            sheet = CharacterSheetFactory()
            CharacterVitals.objects.create(
                character_sheet=sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )
            CharacterAnimaFactory(character=sheet.character, current=10, maximum=10)
            CharacterResonanceFactory(character_sheet=sheet, resonance=resonance, balance=10)
            technique = TechniqueFactory(clash_capable=True)
            CharacterTechniqueFactory(character=sheet, technique=technique)
            ThreadFactory(owner=sheet, resonance=resonance)
            participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
            participants.append(participant)

        # NPC opponent.
        threat_pool = ThreatPoolFactory()
        threat_entry = ThreatPoolEntryFactory(pool=threat_pool, clash_capable=True)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            name=npc_name,
            threat_pool=threat_pool,
            tier=OpponentTier.MOOK,
            health=30,
            max_health=30,
        )

        # Active clash, initiated by PC 1, targeting the opponent.
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            initiator=participants[0].character_sheet,
            triggering_threat_entry=threat_entry,
            started_round=round_number,
        )

        return PlayableCombatScenario(
            scene=scene,
            encounter=encounter,
            participants=participants,
            opponent=opponent,
            clash=clash,
            threat_pool=threat_pool,
            threat_entry=threat_entry,
        )


# =============================================================================
# Boss fight scenario — composition helper, not a DjangoModelFactory (#2095).
# =============================================================================


@dataclass
class BossFightScenario:
    """A fully-composed 3-PC-vs-boss encounter for the break-bar / vulnerability-
    window / phase-transition / enrage journey test.

    Built by ``BossFightScenarioFactory.create()``. The boss carries 3
    ``BossPhase`` rows, each with its own break bar (phase 1's config is also
    stamped directly onto the ``opponent``, mirroring what a real
    ``add_opponent``-driven spawn does for phase 1): phase 2 authors
    ``reinforcement_template``/``reinforcement_count`` (adds spawn on 1→2), and
    phase 3 authors an enraged ``damage_multiplier`` (stamped on 2→3). PCs 1-2
    share a learned combo (``ComboLearning`` already exists — the combo is
    known going in) whose ``bonus_damage`` both chips the break bar
    (``assess_break_bar``) and, bypassing soak, deals real HP damage. The
    threat pool's ``flat_entry`` carries a ``defense_check_type`` (required for
    ``opponent.damage_multiplier`` to apply — see ``resolve_npc_attack``) so
    the enrage delta is provable via a direct before/after damage comparison;
    ``condition_entry`` carries ``conditions_applied`` so an enemy-NPC attack
    landing a condition on a PC is provable via the resolution path.
    """

    scene: object
    encounter: CombatEncounter
    participants: list[CombatParticipant]
    techniques: list[object]
    opponent: CombatOpponent
    phases: list[BossPhase]
    combo: ComboDefinition
    threat_pool: ThreatPool
    flat_entry: ThreatPoolEntry
    condition_entry: ThreatPoolEntry
    condition_template: object
    reinforcement_template: CreatureTemplate
    defense_check_type: object


class BossFightScenarioFactory:
    """Compose a full 3-PC-vs-boss scenario in one call (#2095).

    Wires a Scene + CombatEncounter (DECLARING status) + ``num_pcs`` PC
    ``CombatParticipant``s (character sheet, vitals, anima, fatigue,
    engagement, one technique each of a distinct ``EffectType``) + a
    BOSS-tier ``CombatOpponent`` with 3 authored ``BossPhase`` rows (break
    bar / reinforcement / enrage) + a learned 2-PC combo + a threat pool
    carrying both a flat-damage entry and a condition-applying entry.

    Used by the boss-fight journey test (``test_boss_fight_journey.py``) as
    its scenario builder — mirrors ``PlayableCombatScenarioFactory``'s
    composition style.

    Authored numbers are deterministic by design (not tuned by trial and
    error) — see the journey test's module docstring for the full derivation.
    """

    @classmethod
    def create(cls, *, num_pcs: int = 3) -> BossFightScenario:
        from actions.factories import ActionTemplateFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.checks.factories import CheckTypeFactory
        from world.combat.constants import ComboLearningMethod
        from world.conditions.factories import ConditionTemplateFactory
        from world.fatigue.models import FatiguePool
        from world.magic.factories import (
            CharacterAnimaFactory,
            CharacterTechniqueFactory,
            EffectTypeFactory,
            GiftFactory,
            TechniqueFactory,
        )
        from world.mechanics.factories import CharacterEngagementFactory
        from world.scenes.constants import RoundStatus
        from world.scenes.factories import SceneFactory
        from world.vitals.models import CharacterVitals

        scene = SceneFactory()
        encounter = CombatEncounterFactory(
            scene=scene,
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # --- Threat pool: a flat-damage entry (defense_check_type set so the
        # enrage damage_multiplier applies — see resolve_npc_attack) and a
        # conditions_applied entry (enemy-NPC condition application). ---
        threat_pool = ThreatPoolFactory(name="Boss Threat Pool")
        defense_check_type = CheckTypeFactory(name="Boss Attack Defense")
        # Long duration so the condition survives the multi-round journey rather
        # than decaying away (default ConditionTemplate duration is 3 rounds)
        # before the journey test gets to assert it landed.
        condition_template = ConditionTemplateFactory(
            name="Scorched (Boss Fight)", default_duration_value=50
        )
        flat_entry = ThreatPoolEntryFactory(
            pool=threat_pool,
            name="Claw Swipe",
            base_damage=12,
            defense_check_type=defense_check_type,
        )
        condition_entry = ThreatPoolEntryFactory(
            pool=threat_pool,
            name="Venom Bite",
            base_damage=8,
            defense_check_type=defense_check_type,
        )
        condition_entry.conditions_applied.add(condition_template)

        # --- Boss opponent: phase 1's break bar stamped directly (mirrors what
        # a real spawn does for phase 1 — see _stamp_phase_break_bar_config). ---
        opponent = BossOpponentFactory(
            encounter=encounter,
            name="Factory Boss",
            health=100,
            max_health=100,
            soak_value=15,
            threat_pool=threat_pool,
            current_phase=1,
            break_bar_threshold=6,
            break_bar_current=6,
            vulnerability_rounds=2,
            vulnerability_intensity_bonus=2,
        )

        pool_p2 = ThreatPoolFactory(name="Boss Threat Pool — Phase 2+")
        add_template = CreatureTemplate.objects.create(
            name="Boss Fight Add",
            tier=OpponentTier.MOOK,
            threat_pool=pool_p2,
        )
        phase1 = BossPhaseFactory(
            opponent=opponent,
            phase_number=1,
            threat_pool=threat_pool,
            soak_value=15,
            break_bar_threshold=6,
            vulnerability_rounds=2,
            vulnerability_intensity_bonus=2,
            damage_multiplier=Decimal("1.0"),
        )
        phase2 = BossPhaseFactory(
            opponent=opponent,
            phase_number=2,
            threat_pool=pool_p2,
            soak_value=20,
            health_trigger_percentage=0.70,
            break_bar_threshold=1,
            vulnerability_rounds=2,
            vulnerability_intensity_bonus=2,
            damage_multiplier=Decimal("1.0"),
            reinforcement_template=add_template,
            reinforcement_count=2,
        )
        phase3 = BossPhaseFactory(
            opponent=opponent,
            phase_number=3,
            threat_pool=pool_p2,
            soak_value=10,
            health_trigger_percentage=0.30,
            break_bar_threshold=1,
            vulnerability_rounds=2,
            vulnerability_intensity_bonus=2,
            damage_multiplier=Decimal("2.50"),
        )

        # --- PCs: one technique each of a distinct EffectType. ---
        gift = GiftFactory()
        participants: list[CombatParticipant] = []
        techniques: list[object] = []
        for i in range(num_pcs):
            sheet = CharacterSheetFactory()
            CharacterVitals.objects.create(
                character_sheet=sheet,
                health=100,
                max_health=100,
                base_max_health=100,
            )
            CharacterAnimaFactory(character=sheet.character, current=50, maximum=50)
            FatiguePool.objects.create(character_sheet=sheet)
            CharacterEngagementFactory(character=sheet.character)
            effect_type = EffectTypeFactory(name=f"Boss Fight Effect {i}", base_power=10)
            technique = TechniqueFactory(
                gift=gift,
                effect_type=effect_type,
                action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
            )
            CharacterTechniqueFactory(character=sheet, technique=technique)
            participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
            participants.append(participant)
            techniques.append(technique)

        # --- Learned combo between PCs 1-2 (already known — no discovery needed). ---
        combo = ComboDefinitionFactory(
            name="Boss Fight Combo",
            bonus_damage=10,
            bypass_soak=True,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=techniques[0].effect_type,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=techniques[1].effect_type,
        )
        ComboLearningFactory(
            combo=combo,
            character_sheet=participants[0].character_sheet,
            learned_via=ComboLearningMethod.TRAINING,
        )
        ComboLearningFactory(
            combo=combo,
            character_sheet=participants[1].character_sheet,
            learned_via=ComboLearningMethod.TRAINING,
        )

        return BossFightScenario(
            scene=scene,
            encounter=encounter,
            participants=participants,
            techniques=techniques,
            opponent=opponent,
            phases=[phase1, phase2, phase3],
            combo=combo,
            threat_pool=threat_pool,
            flat_entry=flat_entry,
            condition_entry=condition_entry,
            condition_template=condition_template,
            reinforcement_template=add_template,
            defense_check_type=defense_check_type,
        )


def wire_penetration_check_type():
    """Seed the 'penetration' CheckType for the ward contest (#639, #767, #1706).

    Idempotent — uses CheckTypeFactory's django_get_or_create on (name,
    category); the trait composition is an authoritative rewrite (delete +
    recreate) so a re-seed corrects the prior stat+stat seed and converges.
    Staff weight edits are reset on re-seed (mirrors social_checks.py). The
    check resolves through the shared rank/chart pipeline
    (ResultChart.get_chart_for_difference), so no per-CheckType chart row is
    needed; tests that need a concrete success level force it via
    force_check_outcome or an offense_check_fn override.

    Trait composition (willpower 1.00, intellect 0.50, Melee Combat 0.50):
    willpower mirrors the seeded magical_challenge check so a production
    caster rolls a real pool against the ward; the Melee Combat skill leg
    rewards martial awareness against warded foes (#1706).
    """
    from decimal import Decimal

    from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
    from world.checks.models import CheckTypeTrait
    from world.combat.constants import PENETRATION_CHECK_TYPE_NAME
    from world.seeds.combat_checks import ensure_melee_combat_skill
    from world.traits.factories import StatTraitFactory
    from world.traits.models import TraitCategory

    check_type = CheckTypeFactory(
        name=PENETRATION_CHECK_TYPE_NAME,
        category=CheckCategoryFactory(name="Combat"),
        description="Penetrate a warded target's barrier (#639).",
    )
    skill = ensure_melee_combat_skill()
    composition = [
        (StatTraitFactory(name="willpower", category=TraitCategory.META), Decimal("1.00")),
        (StatTraitFactory(name="intellect", category=TraitCategory.MENTAL), Decimal("0.50")),
        (skill.trait, Decimal("0.50")),
    ]
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    for trait, weight in composition:
        CheckTypeTrait.objects.create(check_type=check_type, trait=trait, weight=weight)
    return check_type


def wire_penetration_modifier_target():
    """Seed the check-scoped 'penetration' ModifierTarget (#767).

    Links the mechanics ModifierTarget to the penetration CheckType through
    the target_check_type OneToOne, so "+penetration vs warded foes" buffs
    are ordinary CharacterModifier rows picked up by the CHARACTER source in
    collect_check_modifiers. Idempotent via django_get_or_create on
    (category, name); the FK link lands on first create and is preserved
    (never overwritten) on re-runs.
    """
    from world.combat.constants import PENETRATION_CHECK_TYPE_NAME
    from world.mechanics.constants import CHECK_CATEGORY_NAME
    from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

    return ModifierTargetFactory(
        name=PENETRATION_CHECK_TYPE_NAME,
        category=ModifierCategoryFactory(name=CHECK_CATEGORY_NAME),
        description="Caster-side bonus to the penetration check vs warded targets.",
        target_check_type=wire_penetration_check_type(),
        is_active=True,
    )


def wire_flee_check_type():
    """Seed the 'flee' CheckType for the flee-attempt check (#878, #1706).

    Idempotent — uses CheckTypeFactory's django_get_or_create on (name,
    category); the trait composition is an authoritative rewrite (delete +
    recreate) so a re-seed corrects the prior stat+stat seed and converges.
    Staff weight edits are reset on re-seed (mirrors social_checks.py). The
    check resolves through the shared rank/chart pipeline
    (ResultChart.get_chart_for_difference), so no per-CheckType chart row is
    needed.

    Trait composition (agility 1.00, wits 0.50, Melee Combat 0.50): agility
    drives the raw physical escape burst; wits reflects situational reading
    and route choice under pressure; the Melee Combat skill leg rewards a
    trained fighter's situational reading (#1706). Both stats are seeded by
    the character seed helpers (_CHALLENGE_STAT_NAMES) so a production
    character rolls a real pool.
    """
    from decimal import Decimal

    from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
    from world.checks.models import CheckTypeTrait
    from world.combat.constants import FLEE_CHECK_TYPE_NAME
    from world.seeds.combat_checks import ensure_melee_combat_skill
    from world.traits.factories import StatTraitFactory
    from world.traits.models import TraitCategory

    check_type = CheckTypeFactory(
        name=FLEE_CHECK_TYPE_NAME,
        category=CheckCategoryFactory(name="Combat"),
        description="Flee-attempt check rolled when a PC declares flee (#878).",
    )
    skill = ensure_melee_combat_skill()
    composition = [
        (StatTraitFactory(name="agility", category=TraitCategory.PHYSICAL), Decimal("1.00")),
        (StatTraitFactory(name="wits", category=TraitCategory.MENTAL), Decimal("0.50")),
        (skill.trait, Decimal("0.50")),
    ]
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    for trait, weight in composition:
        CheckTypeTrait.objects.create(check_type=check_type, trait=trait, weight=weight)
    return check_type


def wire_flee_modifier_target():
    """Seed the check-scoped 'flee' ModifierTarget (#878).

    Links the mechanics ModifierTarget to the flee CheckType through
    the target_check_type OneToOne, so "+flee" buffs are ordinary
    CharacterModifier rows picked up by the CHARACTER source in
    collect_check_modifiers. Idempotent via django_get_or_create on
    (category, name); the FK link lands on first create and is preserved
    (never overwritten) on re-runs.
    """
    from world.combat.constants import FLEE_CHECK_TYPE_NAME
    from world.mechanics.constants import CHECK_CATEGORY_NAME
    from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

    return ModifierTargetFactory(
        name=FLEE_CHECK_TYPE_NAME,
        category=ModifierCategoryFactory(name=CHECK_CATEGORY_NAME),
        description="Character-side bonus to the flee check (cover, boons, conditions).",
        target_check_type=wire_flee_check_type(),
        is_active=True,
    )


def wire_melee_attack_action_template():
    """Seed the combat 'Melee Attack' ActionTemplate (#1706).

    The combat-flavored sibling of the magic standalone cast template
    (``seeds_cast.ensure_technique_cast_content``). Carries the seeded
    'Melee Attack' CheckType so physical techniques roll a combat check
    (strength + Melee Combat) instead of the magic fallback. Also carries the
    seeded 'Combat: Melee Offense' base ConsequencePool (#1995) — the combat
    sibling of the magic 'Magic: Technique Cast' base pool — so a standalone
    melee cast with no flavor chosen still resolves graded consequences rather
    than short-circuiting to check-only. Idempotent — ``get_or_create`` on the
    name; FK re-wiring ensures both links land even on a pre-existing row.
    """
    from actions.constants import ActionTargetType, Pipeline
    from actions.models import ActionTemplate
    from world.checks.models import CheckCategory, CheckType
    from world.combat.seeds_offense import ensure_melee_offense_pool

    # Resolve the 'Melee Attack' CheckType: prefer the authored seed
    # (seed_combat_check_content writes the full composition); fall back to a
    # minimal get_or_create so the wire function is self-sufficient in test
    # setups that haven't run the combat_checks seed (mirrors how
    # get_standalone_cast_template self-seeds the magic template).
    category, _ = CheckCategory.objects.get_or_create(name="Combat")
    check_type, _ = CheckType.objects.get_or_create(
        name="Melee Attack",
        category=category,
        defaults={"description": "A melee attack roll: strength + Melee Combat."},
    )
    pool = ensure_melee_offense_pool()
    template, _ = ActionTemplate.objects.get_or_create(
        name="Melee Attack",
        defaults={
            "check_type": check_type,
            "consequence_pool": pool,
            "category": "combat",
            "pipeline": Pipeline.SINGLE,
            "target_type": ActionTargetType.SINGLE,
            "description": "Standalone resolution spec for a melee attack.",
        },
    )
    changed = []
    if template.check_type_id != check_type.pk:
        template.check_type = check_type
        changed.append("check_type")
    if template.consequence_pool_id != pool.pk:
        template.consequence_pool = pool
        changed.append("consequence_pool")
    if changed:
        template.save(update_fields=changed)
    return template


class DuelChallengeFactory(factory_django.DjangoModelFactory):
    """Factory for DuelChallenge.

    Creates a PENDING duel challenge between two fresh CharacterSheets.
    Override challenger_sheet/challenged_sheet to test uniqueness constraints.
    The room FK mirrors CombatEncounterFactory's lazy_attribute pattern —
    creates a Room ObjectDB only when needed; pass room=None to omit it.
    """

    class Meta:
        model = DuelChallenge

    challenger_sheet = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
    challenged_sheet = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
    status = DuelChallengeStatus.PENDING

    @factory.lazy_attribute
    def room(self) -> object:
        from evennia import create_object

        return create_object(_ROOM_TYPECLASS, key="Duel Challenge Room", nohome=True)


class PvpDuelFactory:
    """Compose a symmetric PvP duel encounter in one call.

    Not a DjangoModelFactory (the duel setup is a service, not a single model).
    Wraps ``create_pvp_duel`` for use in tests and seed paths.

    Usage::

        duel = PvpDuelFactory.create(challenger_sheet=a, challenged_sheet=b, room=room)
        # duel is a CombatEncounter in DECLARING status.
    """

    @classmethod
    def create(
        cls,
        *,
        challenger_sheet: object | None = None,
        challenged_sheet: object | None = None,
        room: object | None = None,
        risk_level: str = RiskLevel.MODERATE,
    ) -> CombatEncounter:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.duels import create_pvp_duel

        if challenger_sheet is None:
            challenger_sheet = CharacterSheetFactory()
        if challenged_sheet is None:
            challenged_sheet = CharacterSheetFactory()
        if room is None:
            room = create_object(_ROOM_TYPECLASS, key="Duel Room", nohome=True)
        return create_pvp_duel(challenger_sheet, challenged_sheet, room, risk_level=risk_level)


class LethalDuelFactory:
    """Compose a lethal PC-vs-significant-NPC duel encounter in one call.

    Not a DjangoModelFactory (the setup is a service, not a single model).
    Wraps ``create_lethal_duel``; creates a fresh ThreatPool when none is
    supplied so callers can omit ``opponent_kwargs`` entirely.

    Usage::

        duel = LethalDuelFactory.create(pc_sheet=sheet, room=room)
        # duel is a CombatEncounter with risk_level=LETHAL in DECLARING status.

        # Custom NPC stats:
        pool = ThreatPoolFactory()
        duel = LethalDuelFactory.create(
            pc_sheet=sheet,
            room=room,
            opponent_kwargs={"name": "The Champion", "max_health": 300, "threat_pool": pool},
            tier=OpponentTier.BOSS,
        )
    """

    @classmethod
    def create(
        cls,
        *,
        pc_sheet: object | None = None,
        room: object | None = None,
        opponent_kwargs: dict | None = None,
        tier: str = OpponentTier.ELITE,
    ) -> CombatEncounter:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.duels import create_lethal_duel

        if pc_sheet is None:
            pc_sheet = CharacterSheetFactory()
        if room is None:
            room = create_object(_ROOM_TYPECLASS, key="Lethal Duel Room", nohome=True)
        if opponent_kwargs is None:
            opponent_kwargs = {
                "name": "Dueling Master",
                "max_health": 200,
                "threat_pool": ThreatPoolFactory(),
            }
        return create_lethal_duel(pc_sheet, opponent_kwargs, room, tier=tier)


def ensure_escalation_pace_check_type() -> object:
    """Get-or-create the 'Escalation Pace' CheckType (#872, extracted for #2013 reuse)."""
    from decimal import Decimal

    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
    from world.traits.factories import StatTraitFactory
    from world.traits.models import TraitCategory

    category, _ = CheckCategory.objects.get_or_create(name="Combat")
    check, _ = CheckType.objects.get_or_create(
        name="Escalation Pace",
        category=category,
        defaults={"description": "Keep control in pace with rising intensity."},
    )
    # #1706 — seed the Escalation Pace check's wits stat leg (split-second
    # reading of rising combat intensity). Idempotent get_or_create.
    CheckTypeTrait.objects.get_or_create(
        check_type=check,
        trait=StatTraitFactory(name="wits", category=TraitCategory.MENTAL),
        defaults={"weight": Decimal("1.00")},
    )
    return check


class EscalationCurveFactory(factory_django.DjangoModelFactory):
    """Factory for EscalationCurve. Doubles as seed content for staff authoring."""

    class Meta:
        model = EscalationCurve

    name = factory.Sequence(lambda n: f"Escalation Curve {n}")
    start_round = 2
    intensity_step = 1
    pace_difficulty_base = 0
    pace_difficulty_per_level = 0
    control_step_on_success = 1
    control_step_on_partial = 0
    control_step_on_botch = -1
    spike_intensity_amount = 2
    spike_minimum_track_points = 1
    peril_spike_intensity_amount = 3
    hated_foe_spike_intensity_amount = 3

    @factory.lazy_attribute
    def pace_check_type(self) -> object:
        return ensure_escalation_pace_check_type()


def wire_flee_config():
    """Seed the FleeConfig singleton (pk=1) + tier modifier rows + starter pool (#878).

    Idempotent — get_or_create at every layer; staff edits to base_difficulty,
    cover_bonus, or individual tier modifiers are preserved on re-runs.

    Starter pool has three label-only consequences (no APPLY_CONDITION effects)
    covering PARTIAL/FAILURE/BOTCH tiers.  APPLY_CONDITION effects are deferred
    until authored ConditionTemplate content lands (#878).

    Tier modifiers seeded:
        SWARM:      -5   (easy to flee a horde)
        MOOK:        0   (baseline)
        ELITE:      +5
        BOSS:       +10
        HERO_KILLER: +20 (nearly impossible solo)
    """
    from actions.models import ConsequencePool, ConsequencePoolEntry
    from world.checks.models import Consequence
    from world.combat.constants import (
        FLEE_BASE_DIFFICULTY,
        FLEE_CHECK_TYPE_NAME,
        FLEE_PARTIAL_SUCCESS_LEVEL,
    )
    from world.combat.models import FleeConfig, FleeTierModifier, OpponentTier
    from world.traits.models import CheckOutcome

    # --- Outcome tiers for the starter pool ---
    # PARTIAL = the escape-at-cost threshold (FLEE_PARTIAL_SUCCESS_LEVEL = -1).
    # FAILURE (-2) and BOTCH (-3) mean the fleer stays in the fight.
    partial_outcome, _ = CheckOutcome.objects.get_or_create(
        name=f"{FLEE_CHECK_TYPE_NAME}_partial",
        defaults={"success_level": FLEE_PARTIAL_SUCCESS_LEVEL},  # -1
    )
    failure_outcome, _ = CheckOutcome.objects.get_or_create(
        name=f"{FLEE_CHECK_TYPE_NAME}_failure",
        defaults={"success_level": -2},
    )
    botch_outcome, _ = CheckOutcome.objects.get_or_create(
        name=f"{FLEE_CHECK_TYPE_NAME}_botch",
        defaults={"success_level": -3},
    )

    # --- Starter consequence pool ---
    pool, _ = ConsequencePool.objects.get_or_create(
        name="Flee Starter Pool",
        defaults={"description": "Starter consequence pool for flee-check outcomes (#878)."},
    )

    # Pool entries — (outcome_tier, label) is the stable natural key.
    # Note: if an outcome row is deleted and recreated, its new pk will cause
    # stale consequence rows to accumulate; avoid deleting seeded outcome rows.
    # label-only consequences: no APPLY_CONDITION effects until authored
    # ConditionTemplate content lands (#878).
    for outcome, label in [
        (partial_outcome, "Winded escape"),
        (failure_outcome, "Cornered"),
        (botch_outcome, "Stumbled badly"),
    ]:
        consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=outcome,
            label=label,
            defaults={
                "weight": 1,
                "character_loss": False,
            },
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=pool,
            consequence=consequence,
        )

    # --- FleeConfig singleton ---
    check_type = wire_flee_check_type()
    config, _ = FleeConfig.objects.get_or_create(
        pk=1,
        defaults={
            "check_type": check_type,
            "base_difficulty": FLEE_BASE_DIFFICULTY,
            "consequence_pool": pool,
        },
    )

    # --- Tier modifier rows ---
    for tier, modifier in [
        (OpponentTier.SWARM, -5),
        (OpponentTier.MOOK, 0),
        (OpponentTier.ELITE, 5),
        (OpponentTier.BOSS, 10),
        (OpponentTier.HERO_KILLER, 20),
    ]:
        FleeTierModifier.objects.get_or_create(
            tier=tier,
            defaults={"difficulty_modifier": modifier},
        )

    return config


# Sentinel parameter value resolved by the flows pipeline to the live event
# payload at dispatch time (FlowExecution variable_mapping seeds "payload";
# "@payload" is the @variable reference). Mirrors world.magic.factories.
_PAYLOAD_PARAM = "@payload"


def _build_escalation_spike_flow() -> object:
    """Build a FlowDefinition with one CALL_SERVICE_FUNCTION step for the spike handler.

    The step calls ``relationship_spike_handler`` with the event payload.
    Shared by both escalation spike TriggerDefinitions (#872).
    """
    from flows.consts import FlowActionChoices
    from flows.factories import FlowStepDefinitionFactory
    from flows.models import FlowDefinition

    flow, _ = FlowDefinition.objects.get_or_create(name="escalation_relationship_spike")
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.combat.escalation.relationship_spike_handler",
            parameters={"payload": _PAYLOAD_PARAM},
        )
    return flow


class EscalationSpikeOnIncapacitatedTriggerDefinitionFactory(factory_django.DjangoModelFactory):
    """TriggerDefinition for the CHARACTER_INCAPACITATED escalation spike (#872).

    Installed on encounter rooms by ``install_escalation_room_triggers``; calls
    the relationship spike handler so bonded co-combatants surge in intensity.
    """

    class Meta:
        model = "flows.TriggerDefinition"
        django_get_or_create = ("name",)

    name = "escalation_spike_on_incapacitated"
    event_name = "character_incapacitated"
    flow_definition = factory.LazyFunction(_build_escalation_spike_flow)
    priority = 50
    base_filter_condition = None  # all filtering happens in the service function


class EscalationSpikeOnKilledTriggerDefinitionFactory(factory_django.DjangoModelFactory):
    """TriggerDefinition for the CHARACTER_KILLED escalation spike (#872)."""

    class Meta:
        model = "flows.TriggerDefinition"
        django_get_or_create = ("name",)

    name = "escalation_spike_on_killed"
    event_name = "character_killed"
    flow_definition = factory.LazyFunction(_build_escalation_spike_flow)
    priority = 50
    base_filter_condition = None  # all filtering happens in the service function


def _build_peril_spike_flow() -> object:
    """Build a FlowDefinition with one CALL_SERVICE_FUNCTION step for the peril handler (#2013)."""
    from flows.consts import FlowActionChoices
    from flows.factories import FlowStepDefinitionFactory
    from flows.models import FlowDefinition

    flow, _ = FlowDefinition.objects.get_or_create(name="escalation_peril_spike")
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.combat.escalation.peril_spike_handler",
            parameters={"payload": _PAYLOAD_PARAM},
        )
    return flow


class EscalationSpikeOnMortalPerilTriggerDefinitionFactory(factory_django.DjangoModelFactory):
    """TriggerDefinition for the CONDITION_APPLIED mortal-peril spike (#2013).

    Installed on encounter rooms by ``install_escalation_room_triggers``
    alongside the two existing spike triggers; all filtering happens in
    ``peril_spike_handler``.
    """

    class Meta:
        model = "flows.TriggerDefinition"
        django_get_or_create = ("name",)

    name = "escalation_spike_on_mortal_peril"
    event_name = "condition_applied"
    flow_definition = factory.LazyFunction(_build_peril_spike_flow)
    priority = 50
    base_filter_condition = None  # all filtering happens in the service function


def _build_encounter_beat_flow() -> object:
    """Build a FlowDefinition with one CALL_SERVICE_FUNCTION step for the beat handler.

    The step calls ``encounter_completed_beat_handler`` with the ENCOUNTER_COMPLETED
    payload. Drives the combat → story-beat auto-wire (#1746).
    """
    from flows.consts import FlowActionChoices
    from flows.factories import FlowStepDefinitionFactory
    from flows.models import FlowDefinition
    from world.combat.beat_wiring import ENCOUNTER_BEAT_TRIGGER_NAME

    flow, _ = FlowDefinition.objects.get_or_create(name=ENCOUNTER_BEAT_TRIGGER_NAME)
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.combat.beat_wiring.encounter_completed_beat_handler",
            parameters={"payload": _PAYLOAD_PARAM},
        )
    return flow


class EncounterBeatTriggerDefinitionFactory(factory_django.DjangoModelFactory):
    """TriggerDefinition for the ENCOUNTER_COMPLETED → beat consumer (#1746).

    Installed on encounter rooms by ``install_encounter_beat_trigger``;
    dispatches the ENCOUNTER_COMPLETED event to ``encounter_completed_beat_handler``,
    which resolves any linked OUTCOME_TIER beat.
    """

    class Meta:
        model = "flows.TriggerDefinition"
        django_get_or_create = ("name",)

    name = "encounter_completed_beat_wiring"
    event_name = "encounter_completed"
    flow_definition = factory.LazyFunction(_build_encounter_beat_flow)
    priority = 40
    base_filter_condition = None


def wire_weapon_damage_modifier_target():
    """Seed the equipment-relevant 'weapon_damage' ModifierTarget (#985).

    Lives in the 'stat' category (EQUIPMENT_RELEVANT_CATEGORIES) so the
    covenant-role equipment walk fires for it. item_mundane_stat_for_target
    returns the equipped item's effective_weapon_damage for this target.
    Idempotent via django_get_or_create on (category, name).
    """
    from world.items.constants import WEAPON_DAMAGE_TARGET_NAME
    from world.mechanics.constants import STAT_CATEGORY_NAME
    from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

    return ModifierTargetFactory(
        name=WEAPON_DAMAGE_TARGET_NAME,
        category=ModifierCategoryFactory(name=STAT_CATEGORY_NAME),
        description="Equipped-weapon mundane damage + covenant-role weapon bonus.",
        is_active=True,
    )


def wire_armor_soak_modifier_target():
    """Seed the equipment-relevant 'armor_soak' ModifierTarget (#985).

    Lives in the 'stat' category (EQUIPMENT_RELEVANT_CATEGORIES) so the
    covenant-role equipment walk fires for it. item_mundane_stat_for_target
    returns the equipped item's effective_armor_soak for this target.
    Idempotent via django_get_or_create on (category, name).
    """
    from world.items.constants import ARMOR_SOAK_TARGET_NAME
    from world.mechanics.constants import STAT_CATEGORY_NAME
    from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

    return ModifierTargetFactory(
        name=ARMOR_SOAK_TARGET_NAME,
        category=ModifierCategoryFactory(name=STAT_CATEGORY_NAME),
        description="Equipped-armor mundane soak + covenant-role soak bonus.",
        is_active=True,
    )


def wire_elevation_advantage_modifier_target():
    """Seed the 'elevation_advantage' ModifierTarget (#2011).

    A flat stat-category bonus read positionally at combat time: when an
    attacker is ELEVATED/AERIAL and the target is not, the bonus feeds into
    the combat check's extra_modifiers. Offensive-only — no penalty for
    firing up. Staff authors CharacterModifier rows against this target to
    set the magnitude. Idempotent via django_get_or_create on (category, name).
    """
    from world.combat.constants import ELEVATION_ADVANTAGE_TARGET_NAME
    from world.mechanics.constants import STAT_CATEGORY_NAME
    from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

    return ModifierTargetFactory(
        name=ELEVATION_ADVANTAGE_TARGET_NAME,
        category=ModifierCategoryFactory(name=STAT_CATEGORY_NAME),
        description="Offensive-only elevation bonus (ELEVATED/AERIAL attacker firing down).",
        is_active=True,
    )


def wire_escalation_content() -> None:
    """Seed the escalation spike trigger definitions (idempotent).

    Creates (get_or_create):
    - "escalation_relationship_spike" FlowDefinition (one CALL_SERVICE_FUNCTION
      step -> world.combat.escalation.relationship_spike_handler)
    - "escalation_spike_on_incapacitated" TriggerDefinition
    - "escalation_spike_on_killed" TriggerDefinition
    - "escalation_peril_spike" FlowDefinition + "escalation_spike_on_mortal_peril"
      TriggerDefinition (#2013)

    Doubles as integration-test setup and staff seed content. Safe to call
    multiple times — does not create duplicates.
    """
    EscalationSpikeOnIncapacitatedTriggerDefinitionFactory()
    EscalationSpikeOnKilledTriggerDefinitionFactory()
    EscalationSpikeOnMortalPerilTriggerDefinitionFactory()


class ThreatRecordFactory(factory_django.DjangoModelFactory):
    """Factory for ThreatRecord (#2020)."""

    class Meta:
        model = ThreatRecord

    encounter = factory.SubFactory(CombatEncounterFactory)
    opponent = factory.SubFactory(
        CombatOpponentFactory, encounter=factory.SelfAttribute("..encounter")
    )
    participant = factory.SubFactory(
        CombatParticipantFactory, encounter=factory.SelfAttribute("..encounter")
    )
    threat_value = 0


class EngagementLockFactory(factory_django.DjangoModelFactory):
    """Factory for EngagementLock (#2020)."""

    class Meta:
        model = EngagementLock

    encounter = factory.SubFactory(CombatEncounterFactory)
    opponent = factory.SubFactory(
        CombatOpponentFactory, encounter=factory.SelfAttribute("..encounter")
    )
    participant = factory.SubFactory(
        CombatParticipantFactory, encounter=factory.SelfAttribute("..encounter")
    )
    status = EngagementLockStatus.ACTIVE
    initiated_by = LockInitiator.THREAT
    started_round = 1
