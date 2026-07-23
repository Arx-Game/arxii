"""Tests for vitals survivability service layer."""

from django.test import TestCase, tag

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassLevelFactory, ClassStageHealthRateFactory
from world.classes.models import PathStage
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    DamageTypeFactory,
    UnconsciousConditionFactory,
)
from world.conditions.models import ConditionInstance
from world.fatigue.tests import setup_stat
from world.traits.constants import PrimaryStat
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import (
    DEATH_BASE_DIFFICULTY,
    DEATH_SCALING_PER_PERCENT,
    KNOCKOUT_BASE_DIFFICULTY,
    KNOCKOUT_SCALING_PER_PERCENT,
    WOUND_BASE_DIFFICULTY,
    WOUND_SCALING_PER_PERCENT,
    CharacterLifeState,
)
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import (
    calculate_death_difficulty,
    calculate_knockout_difficulty,
    calculate_wound_difficulty,
    derive_base_max_health,
    process_damage_consequences,
    recompute_max_health,
)


class CalculateKnockoutDifficultyTest(TestCase):
    def test_at_twenty_percent_returns_base(self) -> None:
        assert calculate_knockout_difficulty(health_pct=0.2) == KNOCKOUT_BASE_DIFFICULTY

    def test_at_ten_percent_harder(self) -> None:
        result = calculate_knockout_difficulty(health_pct=0.1)
        assert result == KNOCKOUT_BASE_DIFFICULTY + (10 * KNOCKOUT_SCALING_PER_PERCENT)

    def test_at_zero_percent_hardest(self) -> None:
        result = calculate_knockout_difficulty(health_pct=0.0)
        assert result == KNOCKOUT_BASE_DIFFICULTY + (20 * KNOCKOUT_SCALING_PER_PERCENT)

    def test_above_threshold_returns_zero(self) -> None:
        assert calculate_knockout_difficulty(health_pct=0.5) == 0

    def test_at_threshold_boundary_returns_base(self) -> None:
        assert calculate_knockout_difficulty(health_pct=0.2) == KNOCKOUT_BASE_DIFFICULTY


class CalculateDeathDifficultyTest(TestCase):
    def test_at_zero_returns_base(self) -> None:
        assert calculate_death_difficulty(health_pct=0.0) == DEATH_BASE_DIFFICULTY

    def test_negative_health_harder(self) -> None:
        result = calculate_death_difficulty(health_pct=-0.2)
        assert result == DEATH_BASE_DIFFICULTY + (20 * DEATH_SCALING_PER_PERCENT)

    def test_above_zero_returns_zero(self) -> None:
        assert calculate_death_difficulty(health_pct=0.1) == 0


class CalculateWoundDifficultyTest(TestCase):
    def test_at_fifty_percent_returns_base(self) -> None:
        assert calculate_wound_difficulty(damage=50, max_health=100) == WOUND_BASE_DIFFICULTY

    def test_higher_damage_harder(self) -> None:
        result = calculate_wound_difficulty(damage=80, max_health=100)
        assert result == WOUND_BASE_DIFFICULTY + (30 * WOUND_SCALING_PER_PERCENT)

    def test_below_threshold_returns_zero(self) -> None:
        assert calculate_wound_difficulty(damage=30, max_health=100) == 0

    def test_zero_max_health_returns_zero(self) -> None:
        assert calculate_wound_difficulty(damage=50, max_health=0) == 0


class ProcessDamageConsequencesTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="survivor")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet,
            health=15,
            max_health=100,
        )
        # Outcome fixtures — used with force_check_outcome
        cls.failure_outcome = CheckOutcomeFactory(name="KO-Failure", success_level=0)
        cls.success_outcome = CheckOutcomeFactory(name="KO-Success", success_level=1)

    def setUp(self) -> None:
        # Reset vitals before each test
        self.vitals.refresh_from_db()
        self.vitals.life_state = CharacterLifeState.ALIVE
        self.vitals.health = 15
        self.vitals.save(update_fields=["life_state", "health"])
        # Clear any conditions applied in previous tests
        from world.conditions.models import ConditionInstance

        ConditionInstance.objects.filter(target=self.character).delete()

    def _seed_knockout_pool_with_failure_unconscious(self) -> None:
        """Wire the knockout pool to a FAILURE-tier consequence applying Unconscious.

        Mirrors the pool model that process_damage_consequences now resolves through.
        """
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from world.checks.constants import EffectType
        from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
        from world.vitals.services import get_vitals_consequence_config

        unconscious_template = UnconsciousConditionFactory()
        consequence = ConsequenceFactory(outcome_tier=self.failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=unconscious_template,
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        cfg = get_vitals_consequence_config()
        cfg.knockout_pool = pool
        cfg.save(update_fields=["knockout_pool"])

    def test_knockout_eligible_success_stays_conscious(self) -> None:
        """Below 20% health + passed check = no FAILURE-tier consequence → no condition."""
        self._seed_knockout_pool_with_failure_unconscious()

        with force_check_outcome(self.success_outcome):
            result = process_damage_consequences(
                character_sheet=self.character.sheet_data,
                damage_dealt=10,
                damage_type=None,
            )
        assert result.knocked_out is False

        from world.conditions.models import ConditionInstance

        assert not ConditionInstance.objects.filter(target=self.character).exists()

    def test_no_pool_seeded_skips_gracefully(self) -> None:
        """When no consequence pool is seeded, the tiers skip — no crash, no consequence.

        This is the graceful-degradation path: a fresh/unseeded DB must not crash
        combat. With no knockout/death/wound pool configured, no condition applies.
        """
        result = process_damage_consequences(
            character_sheet=self.character.sheet_data,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.knocked_out is False
        assert result.dying is False

        from world.conditions.models import ConditionInstance

        assert not ConditionInstance.objects.filter(target=self.character).exists()

    def test_dead_character_is_skipped(self) -> None:
        """A DEAD character (life_state=DEAD) is exempt from further consequences."""
        self.vitals.life_state = CharacterLifeState.DEAD
        self.vitals.save(update_fields=["life_state"])

        result = process_damage_consequences(
            character_sheet=self.character.sheet_data,
            damage_dealt=50,
            damage_type=None,
        )
        # Should return early — no checks performed, message indicates death
        assert result.knocked_out is False
        assert result.dying is False

    def test_no_vitals_returns_default(self) -> None:
        """Character with no CharacterSheet gets a default result.

        Post-OBJECTDB_PARAM refactor takes CharacterSheet | None; None covers
        the "no sheet at all" branch (the function's first guard).
        """
        CharacterFactory(db_key="no_vitals")
        result = process_damage_consequences(
            character_sheet=None,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.message == "No vitals found"


def _build_death_pool_for_bleed_out(*, failure_outcome):
    """Build a failure-tier Bleeding-Out consequence pool (caller wires to a DamageType)."""
    bleed_out = BleedingOutConditionFactory()
    ConditionStageFactory(condition=bleed_out, stage_order=1, name="Bleeding")
    consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.APPLY_CONDITION,
        condition_template=bleed_out,
        target="self",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    return bleed_out, pool


@tag("postgres")
class ProcessDamageConsequencesSourceCharacterTest(TestCase):
    """Thread source_character through process_damage_consequences → Bleeding-Out.

    @tag("postgres"): apply_condition for progressive Bleeding-Out uses the
    PG-only DISTINCT ON query path.
    """

    def setUp(self) -> None:
        ConditionInstance.objects.all().delete()

    def test_bleed_out_carries_source_character(self) -> None:
        """Attacker passed as source_character appears on the resulting ConditionInstance."""
        failure_outcome = CheckOutcomeFactory(name="src-char-death-failure", success_level=-1)
        bleed_out_template, death_pool = _build_death_pool_for_bleed_out(
            failure_outcome=failure_outcome
        )

        attacker = CharacterFactory(db_key="src-attacker")
        victim = CharacterFactory(db_key="src-victim")
        sheet = CharacterSheetFactory(character=victim)
        dtype = DamageTypeFactory(name="src-char-test-dtype")
        dtype.death_pool = death_pool
        dtype.save(update_fields=["death_pool"])

        CharacterVitalsFactory(character_sheet=sheet, health=-5, max_health=100)

        with force_check_outcome(failure_outcome):
            result = process_damage_consequences(
                character_sheet=sheet,
                damage_dealt=30,
                damage_type=dtype,
                source_character=attacker,
            )

        assert result.dying is True, "Death tier must have fired"
        instance = ConditionInstance.objects.filter(
            target=victim, condition=bleed_out_template
        ).first()
        assert instance is not None, "Bleeding-Out ConditionInstance must exist"
        assert instance.source_character == attacker

    def test_no_source_character_yields_none(self) -> None:
        """Calling without source_character leaves ConditionInstance.source_character None."""
        failure_outcome = CheckOutcomeFactory(name="src-char-death-failure-2", success_level=-1)
        bleed_out_template, death_pool = _build_death_pool_for_bleed_out(
            failure_outcome=failure_outcome
        )

        victim2 = CharacterFactory(db_key="src-victim-2")
        sheet2 = CharacterSheetFactory(character=victim2)
        dtype2 = DamageTypeFactory(name="src-char-test-dtype-2")
        dtype2.death_pool = death_pool
        dtype2.save(update_fields=["death_pool"])

        CharacterVitalsFactory(character_sheet=sheet2, health=-5, max_health=100)

        with force_check_outcome(failure_outcome):
            result = process_damage_consequences(
                character_sheet=sheet2,
                damage_dealt=30,
                damage_type=dtype2,
            )

        assert result.dying is True, "Death tier must have fired"
        instance = ConditionInstance.objects.filter(
            target=victim2, condition=bleed_out_template
        ).first()
        assert instance is not None, "Bleeding-Out ConditionInstance must exist"
        assert instance.source_character is None


class CovenantRoleHealthTest(TestCase):
    """Tests for covenant_role_health — level-scaled MAX_HEALTH armor from covenant roles."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CovenantRoleBonusFactory,
            make_engaged_member,
        )
        from world.mechanics.factories import max_health_modifier_target

        # Character engaged in a role with MAX_HEALTH bonus_per_level=4
        cls.character = CharacterFactory(db_key="CovenantHealthChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)
        cls.target = max_health_modifier_target()
        membership = make_engaged_member(character_sheet=cls.sheet)
        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=cls.target,
            bonus_per_level=4,
        )

        # Character with no engaged role
        cls.character_no_role = CharacterFactory(db_key="NoRoleHealthChar")
        CharacterSheetFactory(character=cls.character_no_role, primary_persona=False)

    def test_covenant_role_health_sums_engaged_roles_times_level(self) -> None:
        from world.vitals.services import covenant_role_health

        # 5 * 4 = 20
        self.assertEqual(covenant_role_health(self.character, level=5), 20)

    def test_covenant_role_health_zero_without_engaged_role(self) -> None:
        from world.vitals.services import covenant_role_health

        self.assertEqual(covenant_role_health(self.character_no_role, level=5), 0)


class MaybeDangerRoundOnBleedOutTest(TestCase):
    """Unit tests for _maybe_danger_round_on_bleed_out helper."""

    def setUp(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")

    def _char_in_room(self):
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        sheet.character.db_location = self.room
        sheet.character.save(update_fields=["db_location"])
        return sheet

    def test_non_combat_character_creates_danger_round(self) -> None:
        """A character outside combat causes a DANGER SceneRound to be created."""
        from world.scenes.models import SceneRound
        from world.vitals.services import _maybe_danger_round_on_bleed_out

        sheet = self._char_in_room()
        _maybe_danger_round_on_bleed_out(sheet)
        assert SceneRound.objects.filter(room=self.room).exists()

    def test_in_combat_character_skips_danger_round(self) -> None:
        """A character already in active combat does NOT create a SceneRound."""
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.scenes.constants import RoundStatus
        from world.scenes.models import SceneRound
        from world.vitals.services import _maybe_danger_round_on_bleed_out

        sheet = self._char_in_room()
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING)
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        _maybe_danger_round_on_bleed_out(sheet)
        assert not SceneRound.objects.filter(room=self.room).exists()


class DeriveBaseMaxHealthTest(TestCase):
    """Tests for derive_base_max_health — class stage-rate + stamina + covenant terms."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.vitals.services import get_vitals_consequence_config

        cls.character = CharacterFactory(db_key="HealthDeriveChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)

        # Primary class at level 4 so effective_combat_level returns 4.
        cls.char_class = CharacterClassLevelFactory(
            character=cls.character.sheet_data,
            level=4,
            is_primary=True,
        ).character_class

        # Stage health rates: PROSPECT (levels 1-2) = 10/lvl, POTENTIAL (levels 3-5) = 15/lvl
        ClassStageHealthRateFactory(
            character_class=cls.char_class,
            stage=PathStage.PROSPECT,
            health_per_level=10,
        )
        ClassStageHealthRateFactory(
            character_class=cls.char_class,
            stage=PathStage.POTENTIAL,
            health_per_level=15,
        )

        # Stamina = 6 (internal value 6, display value 0.6 — get_trait_value returns internal)
        setup_stat(cls.character, PrimaryStat.STAMINA, 6)

        # Ensure config singleton exists with weight=3
        cfg = get_vitals_consequence_config()
        cfg.stamina_to_health_weight = 3
        cfg.save(update_fields=["stamina_to_health_weight"])

    def test_derive_sums_class_stamina_and_covenant(self) -> None:
        """Sums class stage-rate term + stamina term + zero covenant term.

        class_term: L1,L2 @PROSPECT=10 → 20; L3,L4 @POTENTIAL=15 → 30; total 50
        stamina_term: 6 * 3 = 18
        covenant_term: 0 (no engaged role)
        expected: 68
        """
        self.assertEqual(derive_base_max_health(self.sheet), 68)

    def test_derive_zero_class_term_without_primary_class(self) -> None:
        """With no primary CharacterClassLevel, class_term is 0; only stamina counts."""
        # Create a fresh character with no class levels and stamina=6
        character = CharacterFactory(db_key="NoClassHealthChar")
        sheet = CharacterSheetFactory(character=character, primary_persona=False)
        setup_stat(character, PrimaryStat.STAMINA, 6)

        # class_term = 0 (no primary class), stamina_term = 6*3 = 18, covenant_term = 0
        self.assertEqual(derive_base_max_health(sheet), 18)


class RecomputeMaxHealthTest(TestCase):
    """Tests for recompute_max_health — derived base vs explicit override + clamp-not-injure."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.vitals.services import get_vitals_consequence_config

        cls.character = CharacterFactory(db_key="RecomputeHealthChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)

        # Primary class at level 4: effective_combat_level returns 4.
        cls.char_class = CharacterClassLevelFactory(
            character=cls.character.sheet_data,
            level=4,
            is_primary=True,
        ).character_class

        # PROSPECT (L1-L2) = 10/lvl, POTENTIAL (L3-L5) = 15/lvl → class_term = 20+30 = 50
        ClassStageHealthRateFactory(
            character_class=cls.char_class,
            stage=PathStage.PROSPECT,
            health_per_level=10,
        )
        ClassStageHealthRateFactory(
            character_class=cls.char_class,
            stage=PathStage.POTENTIAL,
            health_per_level=15,
        )

        # Stamina = 6, weight = 3 → stamina_term = 18
        setup_stat(cls.character, PrimaryStat.STAMINA, 6)

        cfg = get_vitals_consequence_config()
        cfg.stamina_to_health_weight = 3
        cfg.save(update_fields=["stamina_to_health_weight"])
        # derive_base_max_health(cls.sheet) == 68 (50 class + 18 stamina + 0 covenant)

    def setUp(self) -> None:
        # Create a fresh vitals row for each test so mutations don't bleed across tests.
        self.vitals = CharacterVitalsFactory(
            character_sheet=self.sheet,
            base_max_health=None,
            max_health=0,
            health=0,
        )

    def tearDown(self) -> None:
        self.vitals.delete()

    def test_recompute_uses_derived_base_when_override_null(self) -> None:
        """When base_max_health is None, derive_base_max_health(sheet) supplies the base.

        derive_base_max_health returns 68; with thread_addend=5 → max_health == 73.
        """
        result = recompute_max_health(self.sheet, thread_addend=5)
        self.assertEqual(result, 73)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.max_health, 73)

    def test_recompute_uses_override_when_set(self) -> None:
        """When base_max_health is set, that value is used directly."""
        self.vitals.base_max_health = 100
        self.vitals.save(update_fields=["base_max_health"])

        result = recompute_max_health(self.sheet, thread_addend=10)
        self.assertEqual(result, 110)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.max_health, 110)

    def test_recompute_clamp_not_injure_preserved(self) -> None:
        """Clamp-not-injure: current health above new max is clamped down; below is untouched.

        base_max_health=None → derived=68; thread_addend=0 → new_max=68.
        Set current health to 80 (above new max) → clamped to 68.
        Then call again with derived base unchanged → health=40 (below max) → stays 40.
        """
        # Health above new max → clamped down.
        self.vitals.health = 80
        self.vitals.max_health = 80
        self.vitals.save(update_fields=["health", "max_health"])

        recompute_max_health(self.sheet, thread_addend=0)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.max_health, 68)
        self.assertEqual(self.vitals.health, 68)

        # Health below new max → not healed up.
        self.vitals.health = 40
        self.vitals.save(update_fields=["health"])

        recompute_max_health(self.sheet, thread_addend=0)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 40)


class AdvanceStagedPerilTests(TestCase):
    """Regression pin for the ``_advance_staged_peril_condition`` extraction (#1733 Task 3).

    Proves the shared staged-resist-check loop extracted out of ``advance_bleed_out``
    changes no bleed-out behavior — same fixture shape ``advance_surrounded`` will reuse
    once Task 5 lands ``resolve_surrounded_terminal``.

    Builds the ConditionInstance directly (``current_stage`` assigned explicitly) rather
    than via ``apply_condition``, which routes through ``_build_bulk_context``'s PG-only
    ``DISTINCT ON`` query path and errors on the SQLite fast tier (see
    world/vitals/tests/test_bleed_out.py's module docstring for the same constraint).
    """

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet)

    def test_advance_bleed_out_advances_stage_on_failed_resist(self) -> None:
        """A failed resist at a non-terminal stage advances current_stage, doesn't kill."""
        from world.vitals.services import advance_bleed_out

        check_type = CheckTypeFactory()
        template = BleedingOutConditionFactory()
        stage1 = ConditionStageFactory(
            condition=template, stage_order=1, resist_check_type=check_type
        )
        ConditionStageFactory(condition=template, stage_order=2, resist_check_type=check_type)
        ConditionInstanceFactory(
            target=self.sheet.character, condition=template, current_stage=stage1
        )
        failure_outcome = CheckOutcomeFactory(name="Failure 1733 pin", success_level=-1)

        with force_check_outcome(failure_outcome):
            died = advance_bleed_out(self.sheet)

        self.assertFalse(died)
        instance = self.sheet.character.condition_instances.get(condition=template)
        self.assertEqual(instance.current_stage.stage_order, 2)
