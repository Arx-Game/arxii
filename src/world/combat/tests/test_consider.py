"""Tests for the consider band computation and skew logic (#2716)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.combat.consider import (
    COARSE_BANDS,
    FINE_BANDS,
    apply_skew,
    band_prose,
    bias_direction,
    gap_to_band_index,
    health_band,
    skew_for_success_level,
)


class GapToBandIndexTest(TestCase):
    """Level gap maps to the correct band index."""

    def test_coarse_bands_have_five_entries(self) -> None:
        self.assertEqual(len(COARSE_BANDS), 5)

    def test_fine_bands_have_nine_entries(self) -> None:
        self.assertEqual(len(FINE_BANDS), 9)

    def test_coarse_far_above(self) -> None:
        self.assertEqual(gap_to_band_index(5, fine=False), 4)

    def test_coarse_far_below(self) -> None:
        self.assertEqual(gap_to_band_index(-5, fine=False), 0)

    def test_coarse_even_match(self) -> None:
        self.assertEqual(gap_to_band_index(0, fine=False), 2)

    def test_fine_beyond_reckoning(self) -> None:
        self.assertEqual(gap_to_band_index(10, fine=True), 8)

    def test_fine_beneath_notice(self) -> None:
        self.assertEqual(gap_to_band_index(-10, fine=True), 0)

    def test_fine_even_match(self) -> None:
        self.assertEqual(gap_to_band_index(0, fine=True), 4)

    def test_band_prose_returns_correct_string(self) -> None:
        self.assertEqual(band_prose(2, fine=False), "an even match")
        self.assertEqual(band_prose(4, fine=False), "far above you")
        self.assertEqual(band_prose(8, fine=True), "beyond your reckoning")


class SkewForSuccessLevelTest(TestCase):
    """Success level maps to the correct skew magnitude."""

    def test_precise_no_skew(self) -> None:
        self.assertEqual(skew_for_success_level(5), 0)
        self.assertEqual(skew_for_success_level(10), 0)

    def test_solid_no_skew(self) -> None:
        self.assertEqual(skew_for_success_level(1), 0)
        self.assertEqual(skew_for_success_level(4), 0)

    def test_mistaken_skew_one(self) -> None:
        self.assertEqual(skew_for_success_level(0), 1)
        self.assertEqual(skew_for_success_level(-4), 1)

    def test_wildly_wrong_skew_two(self) -> None:
        self.assertEqual(skew_for_success_level(-5), 2)
        self.assertEqual(skew_for_success_level(-9), 2)

    def test_crit_fail_skew_three(self) -> None:
        self.assertEqual(skew_for_success_level(-10), 3)


class BiasDirectionTest(TestCase):
    """Default bias direction is random; the seam is pluggable."""

    @patch("world.combat.consider.random.choice")
    def test_default_returns_plus_or_minus_one(self, mock_choice) -> None:
        mock_choice.return_value = 1
        self.assertEqual(bias_direction(2, 1, character=None), 1)

    @patch("world.combat.consider.random.choice")
    def test_default_can_return_negative(self, mock_choice) -> None:
        mock_choice.return_value = -1
        self.assertEqual(bias_direction(2, 1, character=None), -1)

    def test_zero_skew_returns_zero(self) -> None:
        self.assertEqual(bias_direction(2, 0, character=None), 0)


class ApplySkewTest(TestCase):
    """Skewed band indices clamp to valid range."""

    def test_no_skew_returns_true_index(self) -> None:
        self.assertEqual(apply_skew(2, 0, character=None, max_index=4), 2)

    @patch("world.combat.consider.random.choice")
    def test_skew_up(self, mock_choice) -> None:
        mock_choice.return_value = 1
        self.assertEqual(apply_skew(2, 1, character=None, max_index=4), 3)

    @patch("world.combat.consider.random.choice")
    def test_skew_down(self, mock_choice) -> None:
        mock_choice.return_value = -1
        self.assertEqual(apply_skew(2, 1, character=None, max_index=4), 1)

    @patch("world.combat.consider.random.choice")
    def test_clamp_at_max(self, mock_choice) -> None:
        mock_choice.return_value = 1
        self.assertEqual(apply_skew(4, 2, character=None, max_index=4), 4)

    @patch("world.combat.consider.random.choice")
    def test_clamp_at_zero(self, mock_choice) -> None:
        mock_choice.return_value = -1
        self.assertEqual(apply_skew(0, 2, character=None, max_index=4), 0)


class HealthBandTest(TestCase):
    """Health percentage maps to narrative prose."""

    def test_hale(self) -> None:
        self.assertEqual(health_band(100, 100), "hale and unwounded")
        self.assertEqual(health_band(75, 100), "hale and unwounded")

    def test_wounded(self) -> None:
        self.assertEqual(health_band(74, 100), "wounded but standing")
        self.assertEqual(health_band(50, 100), "wounded but standing")

    def test_bloodied(self) -> None:
        self.assertEqual(health_band(49, 100), "bloodied and flagging")
        self.assertEqual(health_band(25, 100), "bloodied and flagging")

    def test_verge_of_collapse(self) -> None:
        self.assertEqual(health_band(24, 100), "on the verge of collapse")
        self.assertEqual(health_band(1, 100), "on the verge of collapse")

    def test_zero_max_health(self) -> None:
        self.assertEqual(health_band(0, 0), "on the verge of collapse")


class EnhancementDetectionTest(TestCase):
    """_has_engaged_assessment_role follows the reveals_weakness pattern."""

    def test_no_role_returns_false(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.consider import _has_engaged_assessment_role

        sheet = CharacterSheetFactory()
        self.assertFalse(_has_engaged_assessment_role(sheet))

    def test_engaged_role_with_flag_returns_true(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.consider import _has_engaged_assessment_role
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantRoleFactory,
        )

        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(enhances_assessment=True)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant_role=role,
            engaged=True,
        )
        self.assertTrue(_has_engaged_assessment_role(sheet))

    def test_disengaged_role_returns_false(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.consider import _has_engaged_assessment_role
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantRoleFactory,
        )

        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(enhances_assessment=True)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant_role=role,
            engaged=False,
        )
        self.assertFalse(_has_engaged_assessment_role(sheet))


class ConsiderOpponentServiceTest(TestCase):
    """consider_opponent runs the check, caches the reading, returns prose."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.classes.factories import CharacterClassLevelFactory
        from world.combat.constants import (
            OpponentTier,
            ParticipantStatus,
        )
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatOpponentFactory,
            CombatParticipantFactory,
            seed_scaling_defaults,
        )

        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterClassLevelFactory(
            character=cls.participant.character_sheet,
            level=10,
            is_primary=True,
        )
        cls.opponent = CombatOpponentFactory(
            encounter=cls.encounter,
            tier=OpponentTier.MOOK,
            level=10,
        )

    def test_returns_a_reading_with_prose(self) -> None:
        from world.combat.consider import consider_opponent
        from world.combat.models import ConsiderReading

        reading = consider_opponent(self.participant, self.opponent)
        self.assertIsInstance(reading, ConsiderReading)
        self.assertTrue(reading.prose)
        self.assertFalse(reading.is_enhanced)

    def test_caches_reading_no_reroll(self) -> None:
        from world.combat.consider import consider_opponent

        first = consider_opponent(self.participant, self.opponent)
        second = consider_opponent(self.participant, self.opponent)
        self.assertEqual(first.pk, second.pk)

    def test_reading_stores_success_level(self) -> None:
        from world.combat.consider import consider_opponent

        reading = consider_opponent(self.participant, self.opponent)
        self.assertIsNotNone(reading.success_level)

    def test_enhanced_reading_is_flagged(self) -> None:
        from world.combat.consider import consider_opponent
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantRoleFactory,
        )

        role = CovenantRoleFactory(enhances_assessment=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.participant.character_sheet,
            covenant_role=role,
            engaged=True,
        )
        reading = consider_opponent(self.participant, self.opponent)
        self.assertTrue(reading.is_enhanced)
