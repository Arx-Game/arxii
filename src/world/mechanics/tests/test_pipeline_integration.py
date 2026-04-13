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

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.constants import GateRole, Pipeline, ResolutionPhase
from actions.factories import (
    ActionTemplateFactory,
    ActionTemplateGateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from actions.services import get_effective_consequences, start_action_resolution
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.types import CheckResult, ResolutionContext
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    SOULFRAY_CONDITION_NAME,
    check_audere_eligibility,
    end_audere,
    offer_audere,
)
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    IntensityTierFactory,
    MishapPoolTierFactory,
    ResonanceFactory,
    SoulfrayConfigFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
    TechniqueOutcomeModifierFactory,
)
from world.magic.services import get_runtime_technique_stats, use_technique
from world.magic.types import TechniqueUseResult
from world.mechanics.challenge_resolution import resolve_challenge
from world.mechanics.constants import (
    TECHNIQUE_STAT_CATEGORY_NAME,
    CapabilitySourceType,
    PropertyHolder,
    ResolutionType,
)
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    ChallengeTemplatePropertyFactory,
    CharacterEngagementFactory,
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
    PrerequisiteFactory,
    PropertyCategoryFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, CharacterChallengeRecord, ObjectProperty
from world.mechanics.services import (
    get_available_actions,
    get_capability_sources_for_character,
)
from world.mechanics.types import ChallengeResolutionError, DifficultyIndicator
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.types import EnhancedSceneActionResult
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
        cls.primal_property = PropertyFactory(
            name="primal_attuned",
            category=cls.elemental_category,
        )
        cls.prerequisite = PrerequisiteFactory(
            name="has_primal_affinity",
            property=cls.primal_property,
            property_holder=PropertyHolder.SELF,
            minimum_value=1,
        )

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
            target_object=self.location,
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
        assert ctl_src.prerequisite == self.prerequisite
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
        # Give character the prerequisite property so both actions are fully available
        ObjectProperty.objects.create(object=self.character, property=self.primal_property, value=1)
        actions = get_available_actions(self.character, self.location)
        assert len(actions) == 2

        app_names = {a.application_name for a in actions}
        assert app_names == {"Ignite", "Heat Manipulation"}

        for action in actions:
            assert action.challenge_instance_id == self.challenge.id
            assert action.difficulty_indicator is not None
            assert action.prerequisite_met is True

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

    # --- Prerequisite evaluation tests ---

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
    )
    def test_prerequisite_met_when_property_present(
        self,
        mock_diff: object,
    ) -> None:
        """Control capability prerequisite is met when character has the required property."""
        mock_diff.return_value = DifficultyIndicator.MODERATE
        ObjectProperty.objects.create(object=self.character, property=self.primal_property, value=1)
        actions = get_available_actions(self.character, self.location)
        heat_actions = [a for a in actions if a.application_name == "Heat Manipulation"]
        assert len(heat_actions) == 1
        assert all(a.prerequisite_met is True for a in heat_actions)

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
    )
    def test_prerequisite_not_met_when_property_absent(
        self,
        mock_diff: object,
    ) -> None:
        """Control capability prerequisite fails when character lacks the required property."""
        mock_diff.return_value = DifficultyIndicator.MODERATE
        ObjectProperty.objects.filter(object=self.character, property=self.primal_property).delete()
        actions = get_available_actions(self.character, self.location)
        heat_actions = [a for a in actions if a.application_name == "Heat Manipulation"]
        assert len(heat_actions) == 1
        assert all(a.prerequisite_met is False for a in heat_actions)
        assert "primal_attuned" in heat_actions[0].prerequisite_reasons[0]

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
    )
    def test_no_prerequisite_means_always_met(
        self,
        mock_diff: object,
    ) -> None:
        """Generation capability with no prerequisite always shows prerequisite_met=True."""
        mock_diff.return_value = DifficultyIndicator.MODERATE
        actions = get_available_actions(self.character, self.location)
        ignite_actions = [a for a in actions if a.application_name == "Ignite"]
        assert len(ignite_actions) == 1
        assert all(a.prerequisite_met is True for a in ignite_actions)

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


class SceneActionPathTests(PipelineTestMixin, TestCase):
    """Tests for: Technique -> ActionTemplate -> SceneActionRequest -> start_action_resolution()."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # ActionTemplate linked to technique
        cls.action_template = ActionTemplateFactory(
            name="Intimidating Flames",
            check_type=cls.check_type,
            pipeline=Pipeline.SINGLE,
        )
        cls.technique.action_template = cls.action_template
        cls.technique.save(update_fields=["action_template"])

        # Scene setup
        cls.scene = SceneFactory()

        # Initiator persona (our fire mage)
        cls.initiator_persona = PersonaFactory(
            character_sheet=cls.character.sheet_data,
        )

        # Target character and persona
        cls.target_sheet = CharacterSheetFactory()
        cls.target_character = cls.target_sheet.character
        cls.target_persona = PersonaFactory(
            character_sheet=cls.target_sheet,
        )

        # Anima for technique use (required by enhanced action path)
        CharacterAnimaFactory(
            character=cls.character,
            current=50,
            maximum=50,
        )

    def _create_request(self) -> object:
        """Create a SceneActionRequest with action_template and technique set.

        create_action_request() only sets scene/personas/key/status.
        We must set action_template and technique explicitly for the
        resolution pipeline to work.
        """
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="intimidate",
        )
        request.action_template = self.action_template
        request.technique = self.technique
        request.save(update_fields=["action_template", "technique"])
        return request

    def test_scene_action_request_consent_flow(self) -> None:
        """Action request is created in PENDING status with correct links."""
        request = self._create_request()

        assert request.status == ActionRequestStatus.PENDING
        assert request.action_template == self.action_template
        assert request.technique == self.technique
        assert request.initiator_persona == self.initiator_persona
        assert request.target_persona == self.target_persona

    @patch("actions.services.perform_check")
    def test_scene_action_accept_resolves_check(
        self,
        mock_check: object,
    ) -> None:
        """Accepting an action request resolves via perform_check."""
        mock_check.return_value = self._make_check_result(
            self.success_outcome,
        )
        request = self._create_request()

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert isinstance(result, EnhancedSceneActionResult)
        assert result.action_key == "intimidate"
        assert result.action_resolution is not None
        assert result.action_resolution.main_result is not None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED

    def test_scene_action_deny_returns_none(self) -> None:
        """Denying an action request returns None with no check."""
        request = self._create_request()

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )

        assert result is None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.DENIED

    @patch("actions.services.perform_check")
    def test_scene_action_creates_result_interaction(
        self,
        mock_check: object,
    ) -> None:
        """Accepted action creates an Interaction record in the scene."""
        mock_check.return_value = self._make_check_result(
            self.success_outcome,
        )
        request = self._create_request()

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        request.refresh_from_db()
        assert request.result_interaction is not None
        interaction = request.result_interaction
        assert interaction.mode == InteractionMode.ACTION
        assert interaction.scene == self.scene

    @patch("actions.services.perform_check")
    def test_scene_action_failure_still_records(
        self,
        mock_check: object,
    ) -> None:
        """Failed check still records interaction and resolves request."""
        mock_check.return_value = self._make_check_result(
            self.failure_outcome,
        )
        request = self._create_request()

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.action_resolution is not None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.result_interaction is not None

    def test_technique_links_through_action_template(self) -> None:
        """Technique -> ActionTemplate -> CheckType chain is correctly wired."""
        assert self.technique.action_template == self.action_template
        assert self.action_template.check_type == self.check_type


class GatedPipelineTests(PipelineTestMixin, TestCase):
    """Tests for: start_action_resolution() with gated pipeline and pool inheritance."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # Parent pool with generic consequences
        cls.parent_pool = ConsequencePoolFactory(name="Generic Social")
        ConsequencePoolEntryFactory(
            pool=cls.parent_pool,
            consequence=cls.success_consequence,
            weight_override=1,
        )
        ConsequencePoolEntryFactory(
            pool=cls.parent_pool,
            consequence=cls.failure_consequence,
            weight_override=1,
        )

        # Child pool inherits parent, overrides success weight, adds fire consequence
        cls.fire_consequence = ConsequenceFactory(
            outcome_tier=cls.success_outcome,
            label="Wreathed in intimidating fire",
            weight=1,
        )
        cls.child_pool = ConsequencePoolFactory(
            name="Flame Intimidation",
            parent=cls.parent_pool,
        )
        ConsequencePoolEntryFactory(
            pool=cls.child_pool,
            consequence=cls.success_consequence,
            weight_override=3,  # Override parent weight
        )
        ConsequencePoolEntryFactory(
            pool=cls.child_pool,
            consequence=cls.fire_consequence,
        )

        # Gate pool (separate from main pool)
        cls.gate_pool = ConsequencePoolFactory(name="Activation Gate")
        cls.gate_success = ConsequenceFactory(
            outcome_tier=cls.success_outcome,
            label="Gate passed",
            weight=1,
        )
        cls.gate_failure = ConsequenceFactory(
            outcome_tier=cls.failure_outcome,
            label="Gate failed",
            weight=1,
        )
        ConsequencePoolEntryFactory(
            pool=cls.gate_pool,
            consequence=cls.gate_success,
        )
        ConsequencePoolEntryFactory(
            pool=cls.gate_pool,
            consequence=cls.gate_failure,
        )

        # Gated ActionTemplate
        cls.gated_template = ActionTemplateFactory(
            name="Flame Intimidation Template",
            check_type=cls.check_type,
            consequence_pool=cls.child_pool,
            pipeline=Pipeline.GATED,
        )
        cls.gate = ActionTemplateGateFactory(
            action_template=cls.gated_template,
            gate_role=GateRole.ACTIVATION,
            check_type=cls.check_type,
            consequence_pool=cls.gate_pool,
            failure_aborts=True,
        )

    def _make_context(self) -> ResolutionContext:
        return ResolutionContext(character=self.character)

    @patch("actions.services.perform_check")
    def test_gate_failure_aborts_main_step(self, mock_check: object) -> None:
        """Gate failure prevents main step from executing."""
        mock_check.return_value = self._make_check_result(self.failure_outcome)

        resolution = start_action_resolution(
            character=self.character,
            template=self.gated_template,
            target_difficulty=5,
            context=self._make_context(),
        )

        assert resolution.current_phase == ResolutionPhase.GATE_RESOLVED
        assert len(resolution.gate_results) == 1
        assert resolution.gate_results[0].consequence_id == self.gate_failure.id
        assert resolution.main_result is None

    @patch("actions.services.perform_check")
    def test_gate_success_proceeds_to_main(self, mock_check: object) -> None:
        """Gate success allows main step to execute with child pool consequences."""
        mock_check.return_value = self._make_check_result(self.success_outcome)

        resolution = start_action_resolution(
            character=self.character,
            template=self.gated_template,
            target_difficulty=5,
            context=self._make_context(),
        )

        assert resolution.current_phase == ResolutionPhase.COMPLETE
        assert len(resolution.gate_results) == 1
        assert resolution.gate_results[0].consequence_id == self.gate_success.id
        assert resolution.main_result is not None
        # Main consequence comes from child pool (inherited + fire)
        assert resolution.main_result.consequence_id in {
            self.success_consequence.id,
            self.fire_consequence.id,
        }

    def test_pool_inheritance_resolves_correctly(self) -> None:
        """Child pool includes parent entries with overrides applied."""
        effective = get_effective_consequences(self.child_pool)

        # WeightedConsequence has .consequence (model) and .weight
        labels = {c.consequence.label for c in effective}
        assert "Engulfed in flames" in labels  # Parent (overridden weight)
        assert "Fizzles out" in labels  # Parent (inherited)
        assert "Wreathed in intimidating fire" in labels  # Child-only

        # Verify weight override: parent was weight=1, child overrides to 3
        engulfed = next(c for c in effective if c.consequence.label == "Engulfed in flames")
        assert engulfed.weight == 3


class TechniqueUseFlowTests(PipelineTestMixin, TestCase):
    """Tests for the technique use flow wrapping the resolution pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # Dedicated technique for anima flow tests (don't mutate shared mixin
        # technique — SharedMemoryModel cache would poison other test classes)
        cls.flow_technique = TechniqueFactory(
            name="Flame Surge",
            gift=cls.gift,
            intensity=10,
            control=7,
            anima_cost=8,
        )
        TechniqueCapabilityGrantFactory(
            technique=cls.flow_technique,
            capability=cls.generation_cap,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        CharacterTechniqueFactory(
            character=cls.sheet,
            technique=cls.flow_technique,
        )

        # Challenge setup (reuse from ChallengePathTests pattern)
        cls.challenge_template = ChallengeTemplateFactory(
            name="Flame Wall",
            severity=5,
        )
        ChallengeTemplatePropertyFactory(
            challenge_template=cls.challenge_template,
            property=cls.flammable_property,
            value=5,
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.challenge_template,
            consequence=cls.success_consequence,
            resolution_type=ResolutionType.DESTROY,
        )
        cls.burn_approach = ChallengeApproachFactory(
            challenge_template=cls.challenge_template,
            application=cls.ignite_app,
            check_type=cls.check_type,
            display_name="Burn Through",
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=20,
        )
        # Engage the character so social safety bonus does not apply.
        # These tests verify raw base intensity/control math; the social
        # safety bonus (+10 control) would inflate effective_cost and
        # break the delta-formula assertions.
        self.engagement = CharacterEngagementFactory(character=self.character)
        self.challenge = ChallengeInstance.objects.create(
            template=self.challenge_template,
            location=self.location,
            target_object=self.location,
            is_active=True,
            is_revealed=True,
        )

    def _resolve_challenge(self) -> object:
        """Helper that calls resolve_challenge with mocked check."""
        sources = get_capability_sources_for_character(self.character)
        gen_source = next(s for s in sources if s.capability_name == "generation")
        return resolve_challenge(
            self.character,
            self.challenge,
            self.burn_approach,
            gen_source,
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_full_flow_sufficient_anima(self, mock_check: object) -> None:
        """Full technique use: cost calculated, anima deducted, challenge resolved."""
        mock_check.return_value = self._make_check_result(
            self.success_outcome,
        )

        result = use_technique(
            character=self.character,
            technique=self.flow_technique,
            resolve_fn=self._resolve_challenge,
        )

        assert isinstance(result, TechniqueUseResult)
        assert result.confirmed is True
        assert result.resolution_result is not None
        assert result.soulfray_warning is None

        # Anima deducted: base=8, intensity=10, control=7
        # delta = 7 - 10 = -3, effective = max(8 - (-3), 0) = 11
        self.anima.refresh_from_db()
        assert self.anima.current == 20 - 11  # 9

    @patch("world.magic.services.get_soulfray_warning")
    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_soulfray_warning_cancelled_no_resolution(
        self,
        mock_check: object,
        mock_warning: object,
    ) -> None:
        """Player cancels at soulfray warning checkpoint — nothing happens."""
        from world.magic.types import SoulfrayWarning

        mock_warning.return_value = SoulfrayWarning(
            stage_name="Flickering",
            stage_description="Anima flickers dangerously.",
            has_death_risk=False,
        )

        result = use_technique(
            character=self.character,
            technique=self.flow_technique,
            resolve_fn=self._resolve_challenge,
            confirm_soulfray_risk=False,
        )

        assert result.confirmed is False
        assert result.resolution_result is None
        assert result.soulfray_warning is not None
        mock_check.assert_not_called()

        self.anima.refresh_from_db()
        assert self.anima.current == 20

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_overburn_confirmed_resolves_and_drains(
        self,
        mock_check: object,
    ) -> None:
        """Confirmed overburn fully drains anima and resolves."""
        mock_check.return_value = self._make_check_result(
            self.success_outcome,
        )
        self.anima.current = 2
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.flow_technique,
            resolve_fn=self._resolve_challenge,
            confirm_soulfray_risk=True,
        )

        assert result.confirmed is True
        assert result.resolution_result is not None
        assert result.anima_cost.deficit > 0

        self.anima.refresh_from_db()
        assert self.anima.current == 0

    @patch("world.magic.services.select_mishap_pool")
    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_mishap_fires_when_intensity_exceeds_control(
        self,
        mock_check: object,
        mock_pool: object,
    ) -> None:
        """Mishap pool queried when intensity > control."""
        mock_check.return_value = self._make_check_result(
            self.success_outcome,
        )
        mock_pool.return_value = None

        result = use_technique(
            character=self.character,
            technique=self.flow_technique,
            resolve_fn=self._resolve_challenge,
        )

        # Flame Surge: intensity=10, control=7, deficit=3
        mock_pool.assert_called_once_with(3)
        assert result.resolution_result is not None

    def test_high_control_technique_no_mishap(self) -> None:
        """Technique with control >= intensity produces no mishap query."""
        controlled_technique = TechniqueFactory(
            intensity=5,
            control=10,
            anima_cost=2,
            gift=self.gift,
        )
        CharacterTechniqueFactory(
            character=self.sheet,
            technique=controlled_technique,
        )

        with patch("world.magic.services.select_mishap_pool") as mock_pool:
            use_technique(
                character=self.character,
                technique=controlled_technique,
                resolve_fn=lambda: "ok",
            )
            mock_pool.assert_not_called()

    def test_anima_cost_formula_correctness(self) -> None:
        """Verify the delta formula with the test technique's values."""
        # Flame Surge: intensity=10, control=7, anima_cost=8
        # delta = 7 - 10 = -3, effective = max(8 - (-3), 0) = 11
        result = use_technique(
            character=self.character,
            technique=self.flow_technique,
            resolve_fn=lambda: "ok",
        )

        assert result.anima_cost.base_cost == 8
        assert result.anima_cost.control_delta == -3
        assert result.anima_cost.effective_cost == 11

        self.anima.refresh_from_db()
        assert self.anima.current == 9  # 20 - 11


class RuntimeModifierTests(PipelineTestMixin, TestCase):
    """End-to-end tests for the runtime modifier pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.source_ct = ContentType.objects.get_for_model(ObjectDB)

        # ModifierTargets for technique stats
        cls.ts_category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
        cls.intensity_target = ModifierTargetFactory(
            name="intensity",
            category=cls.ts_category,
        )
        cls.control_target = ModifierTargetFactory(
            name="control",
            category=cls.ts_category,
        )

        # Intensity tiers
        cls.minor_tier = IntensityTierFactory(
            name="MinorRT",
            threshold=1,
            control_modifier=0,
        )
        cls.major_tier = IntensityTierFactory(
            name="MajorRT",
            threshold=15,
            control_modifier=-3,
        )

    def tearDown(self) -> None:
        """Clean up any engagement created during tests (OneToOne constraint)."""
        CharacterEngagement.objects.filter(character=self.character).delete()

    # --- Test 1: Social safety bonus without engagement ---

    def test_social_safety_bonus_without_engagement(self) -> None:
        """Unengaged character gets +10 social safety control bonus."""
        stats = get_runtime_technique_stats(self.technique, self.character)
        # technique.control = 7, social safety = +10, minor tier (intensity 10, threshold 1) = +0
        assert stats.control == self.technique.control + 10
        assert stats.intensity == self.technique.intensity

    # --- Test 2: No social safety when engaged ---

    def test_no_social_safety_when_engaged(self) -> None:
        """Engaged character loses the social safety control bonus."""
        # Without engagement — includes social safety
        stats_unengaged = get_runtime_technique_stats(self.technique, self.character)

        # Create engagement
        CharacterEngagementFactory(
            character=self.character,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
        )

        stats_engaged = get_runtime_technique_stats(self.technique, self.character)
        assert stats_engaged.control < stats_unengaged.control
        # Engaged control = base 7 + tier modifier; unengaged = base 7 + 10 + tier modifier
        assert stats_unengaged.control - stats_engaged.control == 10

    # --- Test 3: Engagement process modifiers ---

    def test_engagement_process_modifiers(self) -> None:
        """Engagement intensity_modifier is reflected in runtime stats."""
        CharacterEngagementFactory(
            character=self.character,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
            intensity_modifier=8,
        )

        stats = get_runtime_technique_stats(self.technique, self.character)
        # base intensity 10 + process modifier 8 = 18
        assert stats.intensity == self.technique.intensity + 8

    # --- Test 4: Identity + process modifiers stack ---

    def test_identity_and_process_modifiers_stack(self) -> None:
        """CharacterModifier (identity) + engagement (process) modifiers sum correctly."""
        # Identity modifier: +3 intensity via CharacterModifier
        CharacterModifierFactory(
            character=self.sheet,
            value=3,
            source=DistinctionModifierSourceFactory(),
            target=self.intensity_target,
        )

        # Process modifier: +5 intensity via engagement
        CharacterEngagementFactory(
            character=self.character,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
            intensity_modifier=5,
        )

        stats = get_runtime_technique_stats(self.technique, self.character)
        # base 10 + identity 3 + process 5 = 18
        assert stats.intensity == self.technique.intensity + 3 + 5

    # --- Test 5: IntensityTier control modifier ---

    def test_intensity_tier_control_modifier(self) -> None:
        """High runtime intensity triggers tier-based control penalty."""
        # Create technique with intensity 20 (hits MajorRT tier at threshold 15)
        high_technique = TechniqueFactory(
            name="Inferno Burst",
            gift=self.gift,
            intensity=20,
            control=12,
        )

        # Engage character to remove social safety bonus (cleaner math)
        CharacterEngagementFactory(
            character=self.character,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
        )

        stats = get_runtime_technique_stats(high_technique, self.character)
        # intensity = 20, control = 12 + tier modifier (-3 from MajorRT) = 9
        assert stats.intensity == 20
        assert stats.control == 12 + (-3)

    # --- Test 6: Audere eligibility — all gates ---

    def test_audere_eligibility_all_gates(self) -> None:
        """Audere is eligible when engagement + soulfray stage + intensity gates all pass."""
        # Soulfray condition template with stages
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
        )
        ConditionStageFactory(
            condition=soulfray_template,
            stage_order=1,
            name="Mild Soulfray",
        )
        soulfray_stage_2 = ConditionStageFactory(
            condition=soulfray_template,
            stage_order=2,
            name="Severe Soulfray",
        )

        # Audere condition template (needed for the "not already in Audere" check)
        ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)

        # AudereThreshold requiring major tier and soulfray stage 2
        AudereThresholdFactory(
            minimum_intensity_tier=self.major_tier,
            minimum_warp_stage=soulfray_stage_2,
            intensity_bonus=20,
            anima_pool_bonus=30,
        )

        # Engagement gate
        CharacterEngagementFactory(
            character=self.character,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
        )

        # Soulfray instance at stage 2
        ConditionInstanceFactory(
            target=self.character,
            condition=soulfray_template,
            current_stage=soulfray_stage_2,
        )

        # Runtime intensity 20 hits MajorRT tier (threshold 15)
        assert check_audere_eligibility(self.character, runtime_intensity=20) is True

    # --- Test 7: Audere full lifecycle ---

    def test_audere_full_lifecycle(self) -> None:
        """Engagement -> accept Audere -> boosted stats -> end -> cleanup."""
        # Setup soulfray condition with stages
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
        )
        soulfray_stage = ConditionStageFactory(
            condition=soulfray_template,
            stage_order=1,
            name="Soulfray Stage",
        )

        # Audere condition template
        ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)

        # Threshold config
        threshold = AudereThresholdFactory(
            minimum_intensity_tier=self.minor_tier,
            minimum_warp_stage=soulfray_stage,
            intensity_bonus=20,
            anima_pool_bonus=30,
        )

        # Engagement
        CharacterEngagementFactory(
            character=self.character,
            source_content_type=self.source_ct,
            source_id=self.location.pk,
        )

        # Anima pool
        anima = CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=20,
        )

        # Soulfray instance
        ConditionInstanceFactory(
            target=self.character,
            condition=soulfray_template,
            current_stage=soulfray_stage,
        )

        # Baseline stats (engaged, no Audere yet)
        stats_before = get_runtime_technique_stats(self.technique, self.character)

        # Accept Audere
        result = offer_audere(self.character, accept=True)
        assert result.accepted is True
        assert result.intensity_bonus_applied == 20

        # Stats after Audere — intensity should be boosted
        stats_during = get_runtime_technique_stats(self.technique, self.character)
        assert stats_during.intensity == stats_before.intensity + threshold.intensity_bonus

        # Anima pool should be expanded
        anima.refresh_from_db()
        assert anima.maximum == 20 + threshold.anima_pool_bonus
        assert anima.pre_audere_maximum == 20

        # End Audere
        end_audere(self.character)

        # Stats should revert
        stats_after = get_runtime_technique_stats(self.technique, self.character)
        assert stats_after.intensity == stats_before.intensity

        # Anima pool should revert
        anima.refresh_from_db()
        assert anima.maximum == 20
        assert anima.pre_audere_maximum is None


class SoulfrayProgressionTests(PipelineTestMixin, TestCase):
    """End-to-end tests for the Soulfray accumulation, stage consequence,
    and control mishap streams in use_technique().
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # === 1. Soulfray condition template with 3 severity-driven stages ===
        cls.soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
        )

        # Stage 1: mild, no consequence pool
        cls.soulfray_stage_1 = ConditionStageFactory(
            condition=cls.soulfray_template,
            stage_order=1,
            name="Flickering",
            description="Anima flickers dangerously.",
            severity_threshold=1,
            consequence_pool=None,
        )

        # Stage 2: moderate, has a consequence pool
        cls.soulfray_pool_2 = ConsequencePoolFactory(name="Soulfray Stage 2 Pool")
        cls.soulfray_stage_2 = ConditionStageFactory(
            condition=cls.soulfray_template,
            stage_order=2,
            name="Unstable",
            description="Reality warps around the caster.",
            severity_threshold=10,
            consequence_pool=cls.soulfray_pool_2,
        )

        # Stage 3: severe, consequence pool with character_loss entry
        cls.soulfray_pool_3 = ConsequencePoolFactory(name="Soulfray Stage 3 Pool")
        cls.soulfray_stage_3 = ConditionStageFactory(
            condition=cls.soulfray_template,
            stage_order=3,
            name="Unravelling",
            description="The caster's essence begins to dissolve.",
            severity_threshold=25,
            consequence_pool=cls.soulfray_pool_3,
        )

        # === 2. Resilience check type and outcomes ===
        cls.resilience_check_type = CheckTypeFactory(name="Resilience")
        cls.resilience_success = CheckOutcomeFactory(
            name="Resilience Success",
            success_level=1,
        )
        cls.resilience_failure = CheckOutcomeFactory(
            name="Resilience Failure",
            success_level=-1,
        )
        cls.botch_outcome = CheckOutcomeFactory(
            name="Botch",
            success_level=-3,
        )

        # === 3. ConditionCheckModifiers: escalating penalties ===
        # Exactly one of condition/stage must be set (DB constraint).
        # Use stage-specific modifiers here.
        ConditionCheckModifierFactory(
            condition=None,
            stage=cls.soulfray_stage_1,
            check_type=cls.resilience_check_type,
            modifier_value=-2,
        )
        ConditionCheckModifierFactory(
            condition=None,
            stage=cls.soulfray_stage_2,
            check_type=cls.resilience_check_type,
            modifier_value=-5,
        )
        ConditionCheckModifierFactory(
            condition=None,
            stage=cls.soulfray_stage_3,
            check_type=cls.resilience_check_type,
            modifier_value=-10,
        )

        # === 4. Consequence pools for stages ===

        # Stage 2: success/failure consequences
        cls.soulfray2_success = ConsequenceFactory(
            outcome_tier=cls.resilience_success,
            label="Soulfray contained",
            weight=1,
        )
        cls.soulfray2_failure = ConsequenceFactory(
            outcome_tier=cls.resilience_failure,
            label="Soulfray scars form",
            weight=1,
        )
        cls.magical_scars_template = ConditionTemplateFactory(
            name="Magical Scars",
        )
        ConsequenceEffectFactory(
            consequence=cls.soulfray2_failure,
            effect_type=EffectType.MAGICAL_SCARS,
            target=EffectTarget.SELF,
            condition_template=cls.magical_scars_template,
            condition_severity=1,
        )
        ConsequencePoolEntryFactory(
            pool=cls.soulfray_pool_2,
            consequence=cls.soulfray2_success,
        )
        ConsequencePoolEntryFactory(
            pool=cls.soulfray_pool_2,
            consequence=cls.soulfray2_failure,
        )

        # Stage 3: character_loss consequence
        cls.soulfray3_success = ConsequenceFactory(
            outcome_tier=cls.resilience_success,
            label="Barely survived",
            weight=1,
        )
        cls.soulfray3_death = ConsequenceFactory(
            outcome_tier=cls.resilience_failure,
            label="Consumed by Soulfray",
            weight=1,
            character_loss=True,
        )
        ConsequencePoolEntryFactory(
            pool=cls.soulfray_pool_3,
            consequence=cls.soulfray3_success,
        )
        ConsequencePoolEntryFactory(
            pool=cls.soulfray_pool_3,
            consequence=cls.soulfray3_death,
        )

        # === 5. SoulfrayConfig ===
        cls.soulfray_config = SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
            resilience_check_type=cls.resilience_check_type,
            base_check_difficulty=15,
        )

        # === 6. MishapPoolTier for control deficit mishaps ===
        cls.mishap_pool = ConsequencePoolFactory(name="Control Mishap Pool")
        cls.mishap_consequence = ConsequenceFactory(
            outcome_tier=cls.resilience_success,
            label="Technique misfires",
            weight=1,
        )
        ConsequencePoolEntryFactory(
            pool=cls.mishap_pool,
            consequence=cls.mishap_consequence,
        )
        cls.mishap_tier = MishapPoolTierFactory(
            min_deficit=1,
            max_deficit=None,
            consequence_pool=cls.mishap_pool,
        )

        # === 7. TechniqueOutcomeModifiers ===
        TechniqueOutcomeModifierFactory(
            outcome=cls.botch_outcome,
            modifier_value=-5,
        )
        TechniqueOutcomeModifierFactory(
            outcome=cls.resilience_success,
            modifier_value=2,
        )

        # === 8. Dedicated technique for soulfray tests ===
        # intensity=10, control=7, anima_cost=2 (same as mixin technique)
        cls.soulfray_technique = TechniqueFactory(
            name="Soulfray Test Bolt",
            gift=cls.gift,
            intensity=10,
            control=7,
            anima_cost=2,
        )
        TechniqueCapabilityGrantFactory(
            technique=cls.soulfray_technique,
            capability=cls.generation_cap,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        CharacterTechniqueFactory(
            character=cls.sheet,
            technique=cls.soulfray_technique,
        )

        # High-intensity technique for mishap tests
        # intensity=15, control=5 => deficit=10
        cls.wild_technique = TechniqueFactory(
            name="Wild Surge",
            gift=cls.gift,
            intensity=15,
            control=5,
            anima_cost=2,
        )
        TechniqueCapabilityGrantFactory(
            technique=cls.wild_technique,
            capability=cls.generation_cap,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        CharacterTechniqueFactory(
            character=cls.sheet,
            technique=cls.wild_technique,
        )

    def setUp(self) -> None:
        # Fresh anima per test; engaged to remove social safety bonus
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=10,
            maximum=10,
        )
        self.engagement = CharacterEngagementFactory(
            character=self.character,
        )

    def tearDown(self) -> None:
        """Clean up per-test condition instances and engagement."""
        ConditionInstance.objects.filter(target=self.character).delete()
        CharacterEngagement.objects.filter(
            character=self.character,
        ).delete()

    def _make_resilience_result(
        self,
        outcome: object,
    ) -> CheckResult:
        """Build a CheckResult for the resilience check type."""
        return CheckResult(
            check_type=self.resilience_check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    # ------------------------------------------------------------------
    # Test 1: Full anima — no Soulfray produced
    # ------------------------------------------------------------------

    def test_no_soulfray_above_threshold(self) -> None:
        """With full anima (ratio=1.0 > 0.30), no Soulfray is created."""
        result = use_technique(
            character=self.character,
            technique=self.soulfray_technique,
            resolve_fn=lambda: "ok",
        )

        assert result.soulfray_result is None
        assert not ConditionInstance.objects.filter(
            target=self.character,
            condition=self.soulfray_template,
        ).exists()

    # ------------------------------------------------------------------
    # Test 2: Low anima — Soulfray accumulates
    # ------------------------------------------------------------------

    def test_soulfray_accumulation_from_low_anima(self) -> None:
        """Low anima post-deduction triggers Soulfray condition creation."""
        # anima_cost=2, intensity=10, control=7
        # delta = 7-10 = -3, effective = max(2-(-3), 0) = 5
        # After deduction: current = 10 - 5 = 5, ratio = 5/10 = 0.50
        # Still above threshold 0.30 — so set anima lower.
        # Set current=3: after deduction current=0 (deficit=2),
        # ratio=0/10=0, depletion=(0.30-0)/0.30=1.0, severity=ceil(10*1)=10
        # deficit_component=ceil(5*2)=10, total=20
        self.anima.current = 3
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.soulfray_technique,
            resolve_fn=lambda: "ok",
        )

        assert result.soulfray_result is not None
        assert result.soulfray_result.severity_added > 0

        soulfray = ConditionInstance.objects.get(
            target=self.character,
            condition=self.soulfray_template,
        )
        assert soulfray.severity > 0

    # ------------------------------------------------------------------
    # Test 3: First Soulfray is unwarned
    # ------------------------------------------------------------------

    def test_first_soulfray_is_unwarned(self) -> None:
        """No existing Soulfray => no warning checkpoint, but Soulfray can still
        accumulate from low anima on this cast."""
        self.anima.current = 1
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.soulfray_technique,
            resolve_fn=lambda: "ok",
        )

        # No warning was raised (no pre-existing Soulfray condition)
        assert result.soulfray_warning is None
        assert result.confirmed is True
        # But Soulfray was accumulated
        assert result.soulfray_result is not None
        assert result.soulfray_result.severity_added > 0

    # ------------------------------------------------------------------
    # Test 4: Safety checkpoint from existing Soulfray stage
    # ------------------------------------------------------------------

    def test_safety_checkpoint_from_soulfray_stage(self) -> None:
        """Existing Soulfray at stage 1 triggers the safety checkpoint.
        When confirm_soulfray_risk=False, the cast is cancelled."""
        ConditionInstance.objects.create(
            target=self.character,
            condition=self.soulfray_template,
            current_stage=self.soulfray_stage_1,
            severity=5,
        )

        result = use_technique(
            character=self.character,
            technique=self.soulfray_technique,
            resolve_fn=lambda: "ok",
            confirm_soulfray_risk=False,
        )

        assert result.confirmed is False
        assert result.soulfray_warning is not None
        assert result.soulfray_warning.stage_name == "Flickering"
        # Anima should not have been deducted
        self.anima.refresh_from_db()
        assert self.anima.current == 10

    # ------------------------------------------------------------------
    # Test 5: Resilience check drives Soulfray consequence
    # ------------------------------------------------------------------

    @patch("world.checks.services.perform_check")
    def test_resilience_check_drives_soulfray_consequence(
        self,
        mock_check: object,
    ) -> None:
        """At stage 2 with a consequence pool, a resilience check fires
        and selects a consequence from the pool."""
        mock_check.return_value = self._make_resilience_result(
            self.resilience_failure,
        )

        # Pre-existing Soulfray at stage 2 (severity just at threshold)
        ConditionInstance.objects.create(
            target=self.character,
            condition=self.soulfray_template,
            current_stage=self.soulfray_stage_2,
            severity=10,
        )

        # Low anima to trigger soulfray accumulation
        self.anima.current = 1
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.soulfray_technique,
            resolve_fn=lambda: "ok",
            confirm_soulfray_risk=True,
        )

        assert result.soulfray_result is not None
        assert result.soulfray_result.resilience_check is not None
        mock_check.assert_called_once()
        # The check should have been called with our resilience check type
        call_kwargs = mock_check.call_args
        assert call_kwargs[1]["check_type"] == self.resilience_check_type

    # ------------------------------------------------------------------
    # Test 6: Severity advances stage through pipeline
    # ------------------------------------------------------------------

    def test_severity_advances_stage_through_pipeline(self) -> None:
        """Soulfray at severity=9 (stage 1) advances to stage 2 (threshold=10)
        when enough Soulfray severity is added by a low-anima cast."""
        soulfray_instance = ConditionInstance.objects.create(
            target=self.character,
            condition=self.soulfray_template,
            current_stage=self.soulfray_stage_1,
            severity=9,
        )

        # Set anima so post-deduction produces soulfray severity >= 1
        # effective_cost=5, current=3 => post-deduction=0, deficit=2
        # depletion=1.0, severity=ceil(10*1)=10, deficit_comp=ceil(5*2)=10
        # total severity added = 20 => 9+20=29 => hits stage 3 (threshold 25)
        self.anima.current = 3
        self.anima.save(update_fields=["current"])

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = self._make_resilience_result(
                self.resilience_success,
            )
            result = use_technique(
                character=self.character,
                technique=self.soulfray_technique,
                resolve_fn=lambda: "ok",
                confirm_soulfray_risk=True,
            )

        assert result.soulfray_result is not None
        assert result.soulfray_result.stage_advanced is True
        # Verify the DB reflects the new stage
        soulfray_instance.refresh_from_db()
        assert soulfray_instance.severity > 9

    # ------------------------------------------------------------------
    # Test 7: TechniqueOutcomeModifier affects resilience check
    # ------------------------------------------------------------------

    @patch("world.checks.services.perform_check")
    def test_technique_outcome_modifies_resilience_check(
        self,
        mock_check: object,
    ) -> None:
        """A botch outcome on the main technique check applies a penalty
        modifier to the resilience check via TechniqueOutcomeModifier."""
        mock_check.return_value = self._make_resilience_result(
            self.resilience_failure,
        )

        # Pre-existing Soulfray at stage 2 with consequence pool
        ConditionInstance.objects.create(
            target=self.character,
            condition=self.soulfray_template,
            current_stage=self.soulfray_stage_2,
            severity=10,
        )

        # Set anima so post-deduction stays above stage-3 threshold.
        # soulfray_technique: anima_cost=2, intensity=10, control=7
        # effective_cost = max(2-(-3), 0) = 5
        # current=7 => post-deduction=2, deficit=0
        # ratio=2/10=0.20, depletion=(0.30-0.20)/0.30=0.333
        # severity=ceil(10*0.333)=4, no deficit component
        # total severity: 10+4=14, stays in stage 2 (threshold 10-24)
        self.anima.current = 7
        self.anima.save(update_fields=["current"])

        # Simulate a botch on the main technique check
        botch_result = CheckResult(
            check_type=self.check_type,
            outcome=self.botch_outcome,
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
            technique=self.soulfray_technique,
            resolve_fn=lambda: "ok",
            confirm_soulfray_risk=True,
            check_result=botch_result,
        )

        assert result.soulfray_result is not None
        assert result.soulfray_result.resilience_check is not None
        # Verify the modifier was applied: stage2 penalty (-5) +
        # botch modifier (-5) = -10 total
        call_kwargs = mock_check.call_args[1]
        assert call_kwargs["extra_modifiers"] == -10

    # ------------------------------------------------------------------
    # Test 8: Control mishap fires independently of Soulfray
    # ------------------------------------------------------------------

    def test_control_mishap_fires_independently(self) -> None:
        """Full anima + no Soulfray + high intensity technique =>
        mishap fires from control deficit alone."""
        # Wild Surge: intensity=15, control=5, deficit=10
        # Full anima (10/10), effective cost = max(2-(5-15),0) = 12
        # After deduction: current=0, deficit=2
        # But we want to isolate the mishap — set high anima to avoid soulfray
        self.anima.current = 100
        self.anima.maximum = 100
        self.anima.save(update_fields=["current", "maximum"])

        # Provide a check_result so _resolve_mishap can select from pool
        check_result = CheckResult(
            check_type=self.check_type,
            outcome=self.resilience_success,
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
            technique=self.wild_technique,
            resolve_fn=lambda: "ok",
            check_result=check_result,
        )

        # No Soulfray (ratio > threshold with high anima)
        assert result.soulfray_result is None
        # Mishap should fire: intensity 15 > control 5 => deficit 10
        assert result.mishap is not None
        assert result.mishap.consequence_label == "Technique misfires"

    # ------------------------------------------------------------------
    # Test 9: Full flow — all three consequence streams
    # ------------------------------------------------------------------

    @patch("world.checks.services.perform_check")
    def test_full_flow_all_three_streams(
        self,
        mock_check: object,
    ) -> None:
        """Existing Soulfray + low anima + high intensity technique fires
        all three consequence streams: Soulfray accumulation, stage
        consequence (resilience check), and control mishap."""
        mock_check.return_value = self._make_resilience_result(
            self.resilience_failure,
        )

        # Pre-existing Soulfray at stage 2
        ConditionInstance.objects.create(
            target=self.character,
            condition=self.soulfray_template,
            current_stage=self.soulfray_stage_2,
            severity=10,
        )

        # Low anima for Soulfray accumulation
        self.anima.current = 1
        self.anima.save(update_fields=["current"])

        # Provide check_result so mishap can resolve
        check_result = CheckResult(
            check_type=self.check_type,
            outcome=self.resilience_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        # Wild Surge: intensity=15, control=5 => deficit=10
        result = use_technique(
            character=self.character,
            technique=self.wild_technique,
            resolve_fn=lambda: "ok",
            confirm_soulfray_risk=True,
            check_result=check_result,
        )

        # Stream 1: Soulfray accumulation
        assert result.soulfray_result is not None
        assert result.soulfray_result.severity_added > 0

        # Stream 2: Stage consequence (resilience check fired)
        assert result.soulfray_result.resilience_check is not None

        # Stream 3: Control mishap
        assert result.mishap is not None
