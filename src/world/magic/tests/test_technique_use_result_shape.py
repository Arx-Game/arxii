"""Tests verifying TechniqueUseResult is populated with per-resonance involvement fields.

Covers Task 1 of the corruption-per-cast-hook implementation: new fields on
TechniqueUseResult and the two helpers (_character_is_in_audere,
_build_resonance_involvements) wired into use_technique.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.audere import AUDERE_CONDITION_NAME
from world.magic.factories import (
    CharacterAnimaFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.types import ResonanceInvolvement, TechniqueUseResult
from world.mechanics.factories import CharacterEngagementFactory


class TechniqueUseResultFieldTests(TestCase):
    """Verify the new fields on TechniqueUseResult are populated correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory()
        cls.gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(
            intensity=5,
            control=10,
            anima_cost=3,
            gift=cls.gift,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)

    def test_use_technique_populates_technique_field(self) -> None:
        """result.technique is the technique passed to use_technique."""
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
        )
        assert isinstance(result, TechniqueUseResult)
        assert result.technique == self.technique

    def test_use_technique_populates_was_deficit_when_overburn(self) -> None:
        """was_deficit is True when anima cost exceeds available anima."""
        # Use a high-cost technique with very little anima
        anima = CharacterAnimaFactory(current=1, maximum=20)
        character = anima.character
        CharacterEngagementFactory(character=character)
        expensive_technique = TechniqueFactory(
            intensity=5,
            control=5,
            anima_cost=10,  # will overburn with only 1 current
            gift=self.gift,
        )

        result = use_technique(
            character=character,
            technique=expensive_technique,
            resolve_fn=MagicMock(return_value="ok"),
            confirm_soulfray_risk=True,
        )

        assert result.was_deficit is True
        assert result.anima_cost.deficit > 0

    def test_use_technique_was_deficit_false_when_no_overburn(self) -> None:
        """was_deficit is False when the character has enough anima."""
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert result.was_deficit is False

    @patch("world.magic.services.techniques._resolve_mishap")
    @patch("world.magic.services.techniques.select_mishap_pool")
    def test_use_technique_populates_was_mishap_when_mishap_resolved(
        self,
        mock_pool: MagicMock,
        mock_resolve_mishap: MagicMock,
    ) -> None:
        """was_mishap is True when _resolve_mishap returns a non-None MishapResult."""
        from world.magic.types import MishapResult

        mishap_technique = TechniqueFactory(
            intensity=15,
            control=1,  # control_deficit=14 → triggers mishap path
            anima_cost=3,
            gift=self.gift,
        )
        fake_pool = MagicMock()
        mock_pool.return_value = fake_pool
        fake_mishap = MishapResult(consequence_label="Backlash", applied_effect_ids=[])
        mock_resolve_mishap.return_value = fake_mishap

        from world.checks.factories import CheckTypeFactory
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory

        check_type = CheckTypeFactory()
        outcome = CheckOutcomeFactory()
        check_result = CheckResult(
            check_type=check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        result = use_technique(
            character=self.character,
            technique=mishap_technique,
            resolve_fn=MagicMock(return_value="ok"),
            check_result=check_result,
        )

        assert result.was_mishap is True
        assert result.mishap is fake_mishap

    def test_use_technique_was_mishap_false_when_no_mishap(self) -> None:
        """was_mishap is False for a clean cast with no mishap."""
        result = use_technique(
            character=self.character,
            technique=self.technique,  # control > intensity, no mishap
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert result.was_mishap is False
        assert result.mishap is None

    def test_use_technique_populates_was_audere_when_audere_active(self) -> None:
        """was_audere is True when the character has an active Audere ConditionInstance."""
        audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
        ConditionInstanceFactory(target=self.character, condition=audere_template)

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert result.was_audere is True

    def test_use_technique_was_audere_false_when_not_in_audere(self) -> None:
        """was_audere is False when the character has no Audere condition."""
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert result.was_audere is False

    def test_use_technique_resonance_involvements_per_gift_resonance(self) -> None:
        """resonance_involvements has one entry per resonance on the gift."""
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert len(result.resonance_involvements) == 1
        inv = result.resonance_involvements[0]
        assert isinstance(inv, ResonanceInvolvement)
        assert inv.resonance == self.resonance

    def test_use_technique_resonance_involvements_split_intensity_equally_for_two_resonance_gift(
        self,
    ) -> None:
        """stat_bonus_contribution splits runtime intensity equally across resonances."""
        resonance_b = ResonanceFactory()
        two_res_gift = GiftFactory()
        two_res_gift.resonances.add(self.resonance, resonance_b)
        technique = TechniqueFactory(
            intensity=6,
            control=10,
            anima_cost=2,
            gift=two_res_gift,
        )

        result = use_technique(
            character=self.character,
            technique=technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert len(result.resonance_involvements) == 2
        for inv in result.resonance_involvements:
            # runtime_intensity = 6 (no engagement modifiers set here, just CharacterEngagement
            # with no modifiers); split = 6 // 2 = 3
            assert inv.stat_bonus_contribution == 3

    def test_use_technique_resonance_involvements_includes_combat_pull_spent(self) -> None:
        """thread_pull_resonance_spent sums active CombatPull.resonance_spent per resonance."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatParticipantFactory,
            CombatPullFactory,
        )

        sheet = CharacterSheetFactory(character=self.character)
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=1,
            resonance=self.resonance,
            resonance_spent=7,
        )

        # Invalidate cached_property so the new pull is visible
        self.character.combat_pulls.__dict__.pop("_active", None)

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert len(result.resonance_involvements) == 1
        assert result.resonance_involvements[0].thread_pull_resonance_spent == 7

    def test_use_technique_resonance_involvements_empty_when_gift_has_no_resonances(
        self,
    ) -> None:
        """resonance_involvements is empty tuple when the gift has no resonances."""
        bare_gift = GiftFactory()  # no resonances added
        technique = TechniqueFactory(
            intensity=3,
            control=5,
            anima_cost=2,
            gift=bare_gift,
        )

        result = use_technique(
            character=self.character,
            technique=technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert result.resonance_involvements == ()
