"""Tests for vitals survivability service layer."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import (
    DEATH_BASE_DIFFICULTY,
    DEATH_SCALING_PER_PERCENT,
    KNOCKOUT_BASE_DIFFICULTY,
    KNOCKOUT_SCALING_PER_PERCENT,
    WOUND_BASE_DIFFICULTY,
    WOUND_SCALING_PER_PERCENT,
    CharacterStatus,
)
from world.vitals.models import CharacterVitals
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
        cls.vitals = CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=15,
            max_health=100,
        )

    @patch("world.vitals.services.perform_check")
    def test_knockout_eligible_failure_knocks_out(
        self,
        mock_check: MagicMock,
    ) -> None:
        """Below 20% health + failed check = unconscious."""
        mock_check.return_value = MagicMock(
            outcome=MagicMock(success_level=0),
        )
        from world.checks.factories import CheckTypeFactory

        ko_check = CheckTypeFactory(name="knockout-resistance")

        result = process_damage_consequences(
            character=self.character,
            damage_dealt=10,
            damage_type=None,
            knockout_check_type=ko_check,
        )
        assert result.knocked_out is True
        assert result.final_status == CharacterStatus.UNCONSCIOUS
        self.vitals.refresh_from_db()
        assert self.vitals.status == CharacterStatus.UNCONSCIOUS

    @patch("world.vitals.services.perform_check")
    def test_knockout_eligible_success_stays_conscious(
        self,
        mock_check: MagicMock,
    ) -> None:
        """Below 20% health + passed check = still alive."""
        mock_check.return_value = MagicMock(
            outcome=MagicMock(success_level=1),
        )
        from world.checks.factories import CheckTypeFactory

        ko_check = CheckTypeFactory(name="knockout-success")

        # Reset vitals to alive state
        self.vitals.status = CharacterStatus.ALIVE
        self.vitals.health = 15
        self.vitals.save()

        result = process_damage_consequences(
            character=self.character,
            damage_dealt=10,
            damage_type=None,
            knockout_check_type=ko_check,
        )
        assert result.knocked_out is False
        assert result.final_status == CharacterStatus.ALIVE

    @patch("world.vitals.services.perform_check")
    def test_death_eligible_failure_enters_dying(
        self,
        mock_check: MagicMock,
    ) -> None:
        """At 0% health + failed check = dying."""
        mock_check.return_value = MagicMock(
            outcome=MagicMock(success_level=0),
        )
        from world.checks.factories import CheckTypeFactory

        death_check = CheckTypeFactory(name="death-resistance")

        self.vitals.status = CharacterStatus.ALIVE
        self.vitals.health = 0
        self.vitals.save()

        result = process_damage_consequences(
            character=self.character,
            damage_dealt=10,
            damage_type=None,
            death_check_type=death_check,
        )
        assert result.dying is True
        assert result.dying_final_round is True
        assert result.final_status == CharacterStatus.DYING
        self.vitals.refresh_from_db()
        assert self.vitals.status == CharacterStatus.DYING

    def test_no_check_types_returns_alive(self) -> None:
        """When no check types provided, no checks fire."""
        self.vitals.status = CharacterStatus.ALIVE
        self.vitals.health = 10
        self.vitals.save()

        result = process_damage_consequences(
            character=self.character,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.final_status == CharacterStatus.ALIVE

    def test_not_alive_returns_current_status(self) -> None:
        """Already unconscious character doesn't get checked again."""
        self.vitals.status = CharacterStatus.UNCONSCIOUS
        self.vitals.save()

        result = process_damage_consequences(
            character=self.character,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.final_status == CharacterStatus.UNCONSCIOUS

    def test_no_vitals_returns_default(self) -> None:
        """Character with no vitals gets a default result."""
        no_vitals_char = CharacterFactory(db_key="no_vitals")
        result = process_damage_consequences(
            character=no_vitals_char,
            damage_dealt=5,
            damage_type=None,
        )
        assert result.message == "No vitals found"
