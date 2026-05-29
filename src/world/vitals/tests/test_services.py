"""Tests for vitals survivability service layer."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import UnconsciousConditionFactory
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
    process_damage_consequences,
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
                character=self.character,
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
            character=self.character,
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
            character=self.character,
            damage_dealt=50,
            damage_type=None,
        )
        # Should return early — no checks performed, message indicates death
        assert result.knocked_out is False
        assert result.dying is False

    def test_no_vitals_returns_default(self) -> None:
        """Character with no vitals gets a default result."""
        no_vitals_char = CharacterFactory(db_key="no_vitals")
        result = process_damage_consequences(
            character=no_vitals_char,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.message == "No vitals found"
