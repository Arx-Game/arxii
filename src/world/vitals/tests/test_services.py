"""Tests for vitals survivability service layer."""

from django.test import TestCase, tag

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import BleedingOutConditionFactory, UnconsciousConditionFactory
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

    def test_knockout_eligible_failure_knocks_out(self) -> None:
        """Below 20% health + failed check → Unconscious condition applied.

        SQLite-compatible: UnconsciousConditionFactory has no progression
        (has_progression=False) so apply_condition skips DISTINCT ON queries.
        """
        unconscious_template = UnconsciousConditionFactory()
        ko_check = CheckTypeFactory(name="ko-resistance-failure")

        with force_check_outcome(self.failure_outcome):
            result = process_damage_consequences(
                character=self.character,
                damage_dealt=10,
                damage_type=None,
                knockout_check_type=ko_check,
            )

        assert result.knocked_out is True

        # The Unconscious condition must be active on the character
        from world.conditions.models import ConditionInstance

        assert ConditionInstance.objects.filter(
            target=self.character,
            condition=unconscious_template,
        ).exists(), "Expected an active Unconscious condition after knockout"

        # life_state must still be ALIVE (unconscious ≠ dead)
        self.vitals.refresh_from_db()
        assert self.vitals.life_state == CharacterLifeState.ALIVE

    @tag("postgres")
    def test_death_eligible_failure_enters_dying(self) -> None:
        """At 0% health + failed check → Bleeding Out condition applied.

        Tagged @tag("postgres") because apply_condition for a progressive
        condition (has_progression=True) hits a DISTINCT ON query to select
        the initial stage — a PG-specific feature.
        Run via: just test-parity world.vitals.tests.test_services
        """
        from world.conditions.factories import ConditionStageFactory

        bleed_out_template = BleedingOutConditionFactory()
        # At least one stage so apply_condition can initialize current_stage
        ConditionStageFactory(
            condition=bleed_out_template,
            stage_order=1,
            name="Bleeding",
        )
        death_check = CheckTypeFactory(name="death-resistance-failure")

        self.vitals.health = 0
        self.vitals.save(update_fields=["health"])

        with force_check_outcome(self.failure_outcome):
            result = process_damage_consequences(
                character=self.character,
                damage_dealt=10,
                damage_type=None,
                death_check_type=death_check,
            )

        assert result.dying is True

        # The Bleeding Out condition must be active on the character
        from world.conditions.models import ConditionInstance

        assert ConditionInstance.objects.filter(
            target=self.character,
            condition=bleed_out_template,
        ).exists(), "Expected an active Bleeding Out condition after failed death check"

        # life_state must still be ALIVE (dying ≠ dead; death comes from advance_bleed_out)
        self.vitals.refresh_from_db()
        assert self.vitals.life_state == CharacterLifeState.ALIVE

    def test_knockout_eligible_success_stays_conscious(self) -> None:
        """Below 20% health + passed check = still alive, no condition."""
        UnconsciousConditionFactory()  # template exists but should NOT be applied
        ko_check = CheckTypeFactory(name="knockout-success")

        with force_check_outcome(self.success_outcome):
            result = process_damage_consequences(
                character=self.character,
                damage_dealt=10,
                damage_type=None,
                knockout_check_type=ko_check,
            )
        assert result.knocked_out is False

        from world.conditions.models import ConditionInstance

        assert not ConditionInstance.objects.filter(target=self.character).exists()

    def test_no_check_types_returns_no_consequence(self) -> None:
        """When no check types provided, no checks fire."""
        result = process_damage_consequences(
            character=self.character,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.knocked_out is False
        assert result.dying is False

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

    def test_graceful_degradation_no_template_seeded(self) -> None:
        """When no Unconscious template exists, knockout result is set but no crash.

        Verifies that _apply_consequence_condition is a no-op when the condition
        template has not been seeded into the DB (fresh dev or CI environment).
        """
        # Explicitly ensure no Unconscious template exists
        from world.conditions.constants import UNCONSCIOUS_CONDITION_NAME
        from world.conditions.models import ConditionTemplate

        ConditionTemplate.objects.filter(name=UNCONSCIOUS_CONDITION_NAME).delete()

        ko_check = CheckTypeFactory(name="ko-graceful-degradation")

        with force_check_outcome(self.failure_outcome):
            result = process_damage_consequences(
                character=self.character,
                damage_dealt=10,
                damage_type=None,
                knockout_check_type=ko_check,
            )

        # Must not raise; the flag must still be set
        assert result.knocked_out is True

        # And no condition was applied (template missing)
        from world.conditions.models import ConditionInstance

        assert not ConditionInstance.objects.filter(target=self.character).exists()

    def test_no_vitals_returns_default(self) -> None:
        """Character with no vitals gets a default result."""
        no_vitals_char = CharacterFactory(db_key="no_vitals")
        result = process_damage_consequences(
            character=no_vitals_char,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.message == "No vitals found"
