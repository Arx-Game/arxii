"""
End-to-end integration tests for the technique-to-resolution pipeline.

These tests validate that the full chain connects:
Technique -> CapabilityGrant -> Application -> Challenge/Action -> Resolution

Three test classes share a common character/magic/check setup via PipelineTestMixin.
Each class adds domain-specific setup for its resolution path.

This file is designed to grow as new systems come online. Add test methods
as capabilities, prerequisites, cooperative actions, etc. are implemented.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.types import CheckResult
from world.conditions.factories import CapabilityTypeFactory, ConditionTemplateFactory
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.mechanics.challenge_resolution import resolve_challenge
from world.mechanics.constants import CapabilitySourceType, ResolutionType
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    ChallengeTemplatePropertyFactory,
    PrerequisiteTypeFactory,
    PropertyCategoryFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, CharacterChallengeRecord
from world.mechanics.services import (
    get_available_actions,
    get_capability_sources_for_character,
)
from world.mechanics.types import ChallengeResolutionError, DifficultyIndicator
from world.traits.factories import CheckOutcomeFactory


class PipelineTestMixin:
    """
    Shared setup for pipeline integration tests.

    Builds a realistic fire mage character with:
    - Two capability grants (generation + control) on one technique
    - Effect properties linked via Resonance M2M to Property
    - Two applications targeting the same challenge property via different capabilities
    - Check infrastructure with success/failure outcomes and consequences
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # === 1. Character layer ===
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.location = ObjectDB.objects.create(db_key="TestRoom")

        # === 2. Magic identity ===
        cls.flame_resonance = ResonanceFactory(name="Flame")
        cls.heat_resonance = ResonanceFactory(
            name="Heat",
            affinity=cls.flame_resonance.affinity,
        )
        cls.gift = GiftFactory(name="Pyromancy")
        cls.gift.resonances.add(cls.flame_resonance, cls.heat_resonance)

        cls.technique = TechniqueFactory(
            name="Flame Lance",
            gift=cls.gift,
            intensity=10,
            control=7,
        )

        # === 3. Properties (linked to resonances via M2M) ===
        cls.elemental_category = PropertyCategoryFactory(name="elemental")
        cls.flame_property = PropertyFactory(
            name="flame",
            category=cls.elemental_category,
        )
        cls.heat_property = PropertyFactory(
            name="heat",
            category=cls.elemental_category,
        )
        cls.flammable_property = PropertyFactory(
            name="flammable",
            category=cls.elemental_category,
        )

        # Link resonances to their effect properties via M2M
        cls.flame_resonance.properties.add(cls.flame_property)
        cls.heat_resonance.properties.add(cls.heat_property)

        # === 4. Capabilities and grants ===
        cls.generation_cap = CapabilityTypeFactory(name="generation")
        cls.control_cap = CapabilityTypeFactory(name="control")
        cls.prerequisite = PrerequisiteTypeFactory(name="has_primal_affinity")

        cls.generation_grant = TechniqueCapabilityGrantFactory(
            technique=cls.technique,
            capability=cls.generation_cap,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        cls.control_grant = TechniqueCapabilityGrantFactory(
            technique=cls.technique,
            capability=cls.control_cap,
            base_value=2,
            intensity_multiplier=Decimal("0.5"),
            prerequisite=cls.prerequisite,
        )

        # === 5. Ownership ===
        CharacterGiftFactory(character=cls.sheet, gift=cls.gift)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        # === 6. Applications ===
        cls.ignite_app = ApplicationFactory(
            name="Ignite",
            capability=cls.generation_cap,
            target_property=cls.flammable_property,
        )
        cls.heat_manipulation_app = ApplicationFactory(
            name="Heat Manipulation",
            capability=cls.control_cap,
            target_property=cls.flammable_property,
            required_effect_property=cls.heat_property,
        )

        # === 7. Check infrastructure ===
        cls.check_type = CheckTypeFactory(name="Fire Mastery")
        cls.success_outcome = CheckOutcomeFactory(
            name="Success",
            success_level=1,
        )
        cls.failure_outcome = CheckOutcomeFactory(
            name="Failure",
            success_level=-1,
        )

        # Consequences
        cls.burning_condition = ConditionTemplateFactory(name="Burning")

        cls.success_consequence = ConsequenceFactory(
            outcome_tier=cls.success_outcome,
            label="Engulfed in flames",
            weight=1,
        )
        ConsequenceEffectFactory(
            consequence=cls.success_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=cls.burning_condition,
            condition_severity=3,
        )
        ConsequenceEffectFactory(
            consequence=cls.success_consequence,
            effect_type=EffectType.REMOVE_PROPERTY,
            target=EffectTarget.SELF,
            property=cls.flammable_property,
        )

        cls.failure_consequence = ConsequenceFactory(
            outcome_tier=cls.failure_outcome,
            label="Fizzles out",
            weight=1,
        )

    @classmethod
    def _make_check_result(cls, outcome: object) -> CheckResult:
        """Build a CheckResult for mocking perform_check."""
        return CheckResult(
            check_type=cls.check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )


class ChallengePathTests(PipelineTestMixin, TestCase):
    """Tests for: Technique -> Capability -> Application -> Challenge -> resolve_challenge()."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # Challenge template
        cls.challenge_template = ChallengeTemplateFactory(
            name="Wooden Barricade",
            severity=5,
        )
        ChallengeTemplatePropertyFactory(
            challenge_template=cls.challenge_template,
            property=cls.flammable_property,
            value=5,
        )

        # Consequences on template
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.challenge_template,
            consequence=cls.success_consequence,
            resolution_type=ResolutionType.DESTROY,
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.challenge_template,
            consequence=cls.failure_consequence,
            resolution_type=ResolutionType.PERSONAL,
        )

        # Two approaches via different applications
        cls.burn_approach = ChallengeApproachFactory(
            challenge_template=cls.challenge_template,
            application=cls.ignite_app,
            check_type=cls.check_type,
            display_name="Burn Through",
        )
        cls.heat_approach = ChallengeApproachFactory(
            challenge_template=cls.challenge_template,
            application=cls.heat_manipulation_app,
            check_type=cls.check_type,
            display_name="Heat Warp",
        )

    def setUp(self) -> None:
        # Fresh challenge instance per test (resolution deactivates it)
        self.challenge = ChallengeInstance.objects.create(
            template=self.challenge_template,
            location=self.location,
            is_active=True,
            is_revealed=True,
        )

    # --- Capability source tests ---

    def test_capability_sources_returns_both_grants(self) -> None:
        """Technique with two grants produces two separate capability sources."""
        sources = get_capability_sources_for_character(self.character)
        tech_sources = [s for s in sources if s.source_type == CapabilitySourceType.TECHNIQUE]
        assert len(tech_sources) == 2

        gen_src = next(s for s in tech_sources if s.capability_name == "generation")
        assert gen_src.value == 15  # 5 + 1.0 * 10
        assert gen_src.source_name == "Flame Lance"
        # Both resonance properties linked via M2M
        assert set(gen_src.effect_property_ids) == {
            self.flame_property.id,
            self.heat_property.id,
        }

        ctl_src = next(s for s in tech_sources if s.capability_name == "control")
        assert ctl_src.value == 7  # 2 + 0.5 * 10
        assert ctl_src.prerequisite_id == self.prerequisite.id
        assert set(ctl_src.effect_property_ids) == {
            self.flame_property.id,
            self.heat_property.id,
        }

    # --- Action discovery tests ---

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
    )
    def test_available_actions_returns_both_approaches(
        self,
        mock_diff: object,
    ) -> None:
        """Both approaches are available when capability sources match."""
        mock_diff.return_value = DifficultyIndicator.MODERATE
        actions = get_available_actions(self.character, self.location)
        assert len(actions) == 2

        app_names = {a.application_name for a in actions}
        assert app_names == {"Ignite", "Heat Manipulation"}

        for action in actions:
            assert action.challenge_instance_id == self.challenge.id
            assert action.difficulty_indicator is not None

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
    )
    def test_effect_property_filtering_on_heat_manipulation(
        self,
        mock_diff: object,
    ) -> None:
        """Heat Manipulation requires heat effect property, satisfied by resonance M2M."""
        mock_diff.return_value = DifficultyIndicator.MODERATE
        actions = get_available_actions(self.character, self.location)
        heat_actions = [a for a in actions if a.application_name == "Heat Manipulation"]
        assert len(heat_actions) == 1
        assert heat_actions[0].approach_id == self.heat_approach.id

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
    )
    def test_missing_effect_property_excludes_approach(
        self,
        mock_diff: object,
    ) -> None:
        """A technique without heat resonance cannot use Heat Manipulation."""
        mock_diff.return_value = DifficultyIndicator.MODERATE

        # Create second technique with Flame only (no Heat)
        flame_only_resonance = ResonanceFactory(name="FlameOnly")
        flame_only_resonance.properties.add(self.flame_property)
        flame_gift = GiftFactory(name="BasicFirecraft")
        flame_gift.resonances.add(flame_only_resonance)
        flame_technique = TechniqueFactory(
            name="Firebolt",
            gift=flame_gift,
            intensity=8,
        )
        TechniqueCapabilityGrantFactory(
            technique=flame_technique,
            capability=self.control_cap,
            base_value=3,
            intensity_multiplier=Decimal("1.0"),
        )
        CharacterTechniqueFactory(
            character=self.sheet,
            technique=flame_technique,
        )

        actions = get_available_actions(self.character, self.location)
        heat_actions = [a for a in actions if a.application_name == "Heat Manipulation"]

        # Only the original Flame Lance source has heat, not Firebolt
        heat_source_names = {a.capability_source.source_name for a in heat_actions}
        assert "Flame Lance" in heat_source_names
        assert "Firebolt" not in heat_source_names

    # --- Challenge resolution tests ---

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_resolve_challenge_via_ignite_success(
        self,
        mock_check: object,
    ) -> None:
        """Successful resolution via Ignite deactivates challenge and applies effects."""
        mock_check.return_value = self._make_check_result(
            self.success_outcome,
        )

        sources = get_capability_sources_for_character(self.character)
        gen_source = next(s for s in sources if s.capability_name == "generation")

        result = resolve_challenge(
            self.character,
            self.challenge,
            self.burn_approach,
            gen_source,
        )

        assert result.consequence.label == "Engulfed in flames"
        assert result.challenge_deactivated is True
        assert result.resolution_type == ResolutionType.DESTROY
        assert len(result.applied_effects) == 2
        assert CharacterChallengeRecord.objects.filter(
            character=self.character,
            challenge_instance=self.challenge,
        ).exists()

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_resolve_challenge_via_heat_warp_success(
        self,
        mock_check: object,
    ) -> None:
        """Both approaches resolve through the same pipeline."""
        mock_check.return_value = self._make_check_result(
            self.success_outcome,
        )

        sources = get_capability_sources_for_character(self.character)
        ctl_source = next(s for s in sources if s.capability_name == "control")

        result = resolve_challenge(
            self.character,
            self.challenge,
            self.heat_approach,
            ctl_source,
        )

        assert result.consequence.label == "Engulfed in flames"
        assert result.challenge_deactivated is True

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_resolve_challenge_failure_keeps_active(
        self,
        mock_check: object,
    ) -> None:
        """Failed resolution keeps challenge active with PERSONAL resolution."""
        mock_check.return_value = self._make_check_result(
            self.failure_outcome,
        )

        sources = get_capability_sources_for_character(self.character)
        gen_source = next(s for s in sources if s.capability_name == "generation")

        result = resolve_challenge(
            self.character,
            self.challenge,
            self.burn_approach,
            gen_source,
        )

        assert result.consequence.label == "Fizzles out"
        assert result.challenge_deactivated is False
        assert result.resolution_type == ResolutionType.PERSONAL
        assert len(result.applied_effects) == 0
        assert CharacterChallengeRecord.objects.filter(
            character=self.character,
            challenge_instance=self.challenge,
        ).exists()

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_duplicate_resolution_prevented(
        self,
        mock_check: object,
    ) -> None:
        """Cannot resolve the same challenge twice with the same character."""
        mock_check.return_value = self._make_check_result(
            self.failure_outcome,
        )

        sources = get_capability_sources_for_character(self.character)
        gen_source = next(s for s in sources if s.capability_name == "generation")

        resolve_challenge(
            self.character,
            self.challenge,
            self.burn_approach,
            gen_source,
        )

        with self.assertRaises(ChallengeResolutionError):
            resolve_challenge(
                self.character,
                self.challenge,
                self.burn_approach,
                gen_source,
            )
