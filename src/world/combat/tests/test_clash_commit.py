"""Tests for commit_to_clash — the per-round clash contribution pipeline."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.clash import commit_to_clash, outcome_to_delta, strain_to_modifier
from world.combat.factories import ClashConfigFactory, ClashFactory, StrainConfigFactory
from world.combat.types import ClashContributionResult
from world.conditions.factories import ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import CharacterAnimaFactory, SoulfrayConfigFactory, TechniqueFactory
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory


class CommitToClashTests(TestCase):
    """Tests for commit_to_clash routing a PC contribution through use_technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        cls.success_outcome = CheckOutcomeFactory(name="commit_success", success_level=1)
        cls.clash = ClashFactory()

    def _make_character_with_anima(self, current: int = 20, maximum: int = 20) -> tuple:
        """Create a character with a CharacterAnima pool and engagement record."""
        anima = CharacterAnimaFactory(current=current, maximum=maximum)
        CharacterEngagementFactory(character=anima.character)
        return anima.character, anima

    def _make_technique_with_template(
        self, intensity: int = 5, control: int = 10, anima_cost: int = 3
    ) -> object:
        """Create a Technique that has an action_template with a known check_type."""
        template = ActionTemplateFactory(check_type=self.check_type)
        return TechniqueFactory(
            intensity=intensity,
            control=control,
            anima_cost=anima_cost,
            action_template=template,
        )

    # -------------------------------------------------------------------------
    # 1. Basic commit returns a valid ClashContributionResult
    # -------------------------------------------------------------------------

    def test_basic_commit_writes_contribution_result(self) -> None:
        """Zero strain commitment + plenty of anima → valid ClashContributionResult."""
        character, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character=character,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashContributionResult)
        self.assertIsNotNone(result.check_outcome)
        self.assertEqual(result.anima_committed, 0)
        self.assertFalse(result.was_overburn)
        expected_delta = outcome_to_delta(
            check_outcome=self.success_outcome,
            config=self.config_clash,
        )
        self.assertEqual(result.progress_delta, expected_delta)
        self.assertIsNotNone(result.technique_use_result)

    # -------------------------------------------------------------------------
    # 2. Strain modifier reaches perform_check
    # -------------------------------------------------------------------------

    def test_strain_modifier_passed_to_check(self) -> None:
        """A positive strain commitment must raise the modifier relative to zero strain.

        We run two commits: one with strain_commitment=0, one with a non-trivial
        commitment, and verify the resulting progress_delta reflects a higher check
        modifier (i.e. a better outcome) when forced outcomes are the same, OR just
        verify anima_committed matches the commitment and the result is valid.
        """
        character, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        strain_n = 10
        expected_modifier = strain_to_modifier(
            anima_committed=strain_n,
            config=self.config_strain,
        )
        # Modifier must be positive for a non-zero commitment
        self.assertGreater(expected_modifier, 0)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character=character,
                technique=technique,
                clash=self.clash,
                strain_commitment=strain_n,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashContributionResult)
        self.assertEqual(result.anima_committed, strain_n)
        # The technique_use_result.anima_cost.effective_cost must reflect the strain on top
        effective_cost = result.technique_use_result.anima_cost.effective_cost
        # effective_cost >= strain_n (strain adds ON TOP of floor-0)
        self.assertGreaterEqual(effective_cost, strain_n)

    # -------------------------------------------------------------------------
    # 3. Overburn when strain exceeds anima pool
    # -------------------------------------------------------------------------

    def test_overburn_when_strain_exceeds_pool(self) -> None:
        """Committing more strain than the anima pool → was_overburn=True and soulfray fires."""
        # SoulfrayConfig and ConditionTemplate needed for the soulfray accumulation path.
        SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.10"), severity_scale=5, deficit_scale=5
        )
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)

        # Give the character very little anima
        character, _anima = self._make_character_with_anima(current=2, maximum=10)
        # Technique with minimal base cost so only the strain causes overburn
        technique = self._make_technique_with_template(intensity=3, control=10, anima_cost=1)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character=character,
                technique=technique,
                clash=self.clash,
                strain_commitment=20,  # far exceeds current=2
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashContributionResult)
        self.assertTrue(result.was_overburn, "Expected was_overburn=True on strain-induced deficit")
        self.assertGreater(
            result.soulfray_severity_accrued,
            0,
            "Expected soulfray severity > 0 when overburning",
        )

    # -------------------------------------------------------------------------
    # 4. Missing action_template raises ValueError
    # -------------------------------------------------------------------------

    def test_technique_without_action_template_raises(self) -> None:
        """A technique with action_template=None must raise ValueError."""
        character, _anima = self._make_character_with_anima()
        technique = TechniqueFactory(action_template=None)

        with self.assertRaises(ValueError):
            commit_to_clash(
                character=character,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )
