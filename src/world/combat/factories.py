"""FactoryBoy factories for combat models."""

import factory
from factory import django as factory_django

from world.combat.constants import (
    DEFAULT_PACE_TIMER_MINUTES,
    ActionCategory,
    ClashActionSlot,
    ClashFlavor,
    ComboLearningMethod,
    EncounterType,
    LockPcRole,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.models import (
    BossPhase,
    Clash,
    ClashConfig,
    ClashContribution,
    ClashRound,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatPull,
    CombatPullResolvedEffect,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    StrainConfig,
    ThreatPool,
    ThreatPoolEntry,
)
from world.magic.constants import EffectKind

# Factory-path string for the CharacterSheet sub-factory, referenced by
# multiple factories below. Centralized to avoid the duplicated-literal
# SonarCloud smell (python:S1192).
_CHARACTER_SHEET_FACTORY = "world.character_sheets.factories.CharacterSheetFactory"


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

        return create_object("typeclasses.rooms.Room", key="Test Combat Room", nohome=True)


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
        from world.combat.constants import EncounterStatus
        from world.magic.factories import (
            CharacterAnimaFactory,
            CharacterResonanceFactory,
            CharacterTechniqueFactory,
            ResonanceFactory,
            TechniqueFactory,
            ThreadFactory,
        )
        from world.scenes.factories import SceneFactory
        from world.vitals.models import CharacterVitals

        # Singletons (idempotent via django_get_or_create).
        ClashConfigFactory()
        StrainConfigFactory()

        # Scene + encounter.
        scene = SceneFactory()
        encounter = CombatEncounterFactory(
            scene=scene,
            status=EncounterStatus.DECLARING,
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


def wire_penetration_check_type():
    """Seed the 'penetration' CheckType for the ward contest (#639, #767).

    Idempotent — uses CheckTypeFactory's django_get_or_create on (name,
    category) and get_or_create on (check_type, trait), so re-runs are
    no-ops and staff weight edits are preserved. The check resolves through
    the shared rank/chart pipeline (ResultChart.get_chart_for_difference),
    so no per-CheckType chart row is needed; tests that need a concrete
    success level force it via force_check_outcome or an offense_check_fn
    override.

    Trait composition (willpower 1.00, intellect 0.50) mirrors the seeded
    magical_challenge check so a production caster rolls a real pool against
    the ward instead of trait_points=0.
    """
    from decimal import Decimal

    from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
    from world.checks.models import CheckTypeTrait
    from world.combat.constants import PENETRATION_CHECK_TYPE_NAME
    from world.traits.factories import StatTraitFactory
    from world.traits.models import TraitCategory

    check_type = CheckTypeFactory(
        name=PENETRATION_CHECK_TYPE_NAME,
        category=CheckCategoryFactory(name="Combat"),
        description="Penetrate a warded target's barrier (#639).",
    )
    for trait_name, category, weight in [
        ("willpower", TraitCategory.META, "1.00"),
        ("intellect", TraitCategory.MENTAL, "0.50"),
    ]:
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type,
            trait=StatTraitFactory(name=trait_name, category=category),
            defaults={"weight": Decimal(weight)},
        )
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
    """Seed the 'flee' CheckType for the flee-attempt check (#878).

    Idempotent — uses CheckTypeFactory's django_get_or_create on (name,
    category) and get_or_create on (check_type, trait), so re-runs are
    no-ops and staff weight edits are preserved. The check resolves through
    the shared rank/chart pipeline (ResultChart.get_chart_for_difference),
    so no per-CheckType chart row is needed.

    Trait composition (agility 1.00, wits 0.50): agility drives the raw
    physical escape burst; wits reflects situational reading and route
    choice under pressure. Both are seeded by the character seed helpers
    (_CHALLENGE_STAT_NAMES) so a production character rolls a real pool.
    """
    from decimal import Decimal

    from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
    from world.checks.models import CheckTypeTrait
    from world.combat.constants import FLEE_CHECK_TYPE_NAME
    from world.traits.factories import StatTraitFactory
    from world.traits.models import TraitCategory

    check_type = CheckTypeFactory(
        name=FLEE_CHECK_TYPE_NAME,
        category=CheckCategoryFactory(name="Combat"),
        description="Flee-attempt check rolled when a PC declares flee (#878).",
    )
    for trait_name, category, weight in [
        ("agility", TraitCategory.PHYSICAL, "1.00"),
        ("wits", TraitCategory.MENTAL, "0.50"),
    ]:
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type,
            trait=StatTraitFactory(name=trait_name, category=category),
            defaults={"weight": Decimal(weight)},
        )
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
