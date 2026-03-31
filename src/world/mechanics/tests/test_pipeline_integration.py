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

from actions.constants import GateRole, Pipeline, ResolutionPhase
from actions.factories import (
    ActionTemplateFactory,
    ActionTemplateGateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from actions.services import get_effective_consequences, start_action_resolution
from actions.types import SceneActionResult
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.types import CheckResult, ResolutionContext
from world.conditions.factories import CapabilityTypeFactory, ConditionTemplateFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.types import TechniqueUseResult
from world.mechanics.challenge_resolution import resolve_challenge
from world.mechanics.constants import CapabilitySourceType, PropertyHolder, ResolutionType
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    ChallengeTemplatePropertyFactory,
    CharacterEngagementFactory,
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
    """Tests for: Technique -> ActionTemplate -> SceneActionRequest -> resolve_scene_action()."""

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
            character_identity__character=cls.character,
            character=cls.character,
        )

        # Target character and persona
        cls.target_sheet = CharacterSheetFactory()
        cls.target_character = cls.target_sheet.character
        cls.target_persona = PersonaFactory(
            character_identity__character=cls.target_character,
            character=cls.target_character,
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

        assert isinstance(result, SceneActionResult)
        assert result.success is True
        assert result.action_key == "intimidate"
        assert result.check_outcome == "Success"
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

        assert result.success is False
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
        assert result.overburn_severity is None

        # Anima deducted: base=8, intensity=10, control=7
        # delta = 7 - 10 = -3, effective = max(8 - (-3), 0) = 11
        self.anima.refresh_from_db()
        assert self.anima.current == 20 - 11  # 9

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_overburn_cancelled_no_resolution(
        self,
        mock_check: object,
    ) -> None:
        """Player cancels at overburn checkpoint — nothing happens."""
        self.anima.current = 2
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.flow_technique,
            resolve_fn=self._resolve_challenge,
            confirm_overburn=False,
        )

        assert result.confirmed is False
        assert result.resolution_result is None
        assert result.overburn_severity is not None
        mock_check.assert_not_called()

        self.anima.refresh_from_db()
        assert self.anima.current == 2

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
            confirm_overburn=True,
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
